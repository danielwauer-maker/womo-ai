import json
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import CaptureSnapshot, ImportState, Listing
from .repository import upsert_listing
from .scoring import SearchCriteria, score_listing
from .text_enrichment import extract_listing_text

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _source_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "kleinanzeigen" in host:
        return "Kleinanzeigen"
    if "mobile.de" in host:
        return "mobile.de"
    if "autoscout24" in host:
        return "AutoScout24"
    if "caraworld" in host:
        return "Caraworld"
    return host.replace("www.", "") or "capture"


def _clean_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _safe_json_list(value: str, limit: int = 100) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    result = []
    seen = set()
    for item in parsed[:limit]:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _walk_json(value, result: dict) -> None:
    if isinstance(value, list):
        for item in value:
            _walk_json(item, result)
        return
    if not isinstance(value, dict):
        return

    for key, raw in value.items():
        lowered = str(key).lower()
        if lowered in {"name", "headline"} and not result.get("title") and isinstance(raw, str):
            result["title"] = raw.strip()
        elif lowered == "description" and not result.get("description") and isinstance(raw, str):
            result["description"] = raw.strip()
        elif lowered in {"price", "lowprice"} and result.get("price") is None:
            digits = re.sub(r"[^0-9]", "", str(raw))
            if digits:
                candidate = int(digits)
                if 500 <= candidate <= 500000:
                    result["price"] = candidate
        elif lowered in {"datevehiclefirstregistered", "vehiclemodeldate", "modeldate", "productiondate"} and result.get("year") is None:
            m = re.search(r"(19[7-9]\d|20[0-2]\d)", str(raw))
            if m:
                result["year"] = int(m.group(1))
        elif lowered in {"mileagefromodometer", "mileage"} and result.get("mileage") is None:
            if isinstance(raw, dict):
                raw = raw.get("value") or raw.get("valueReference") or ""
            digits = re.sub(r"[^0-9]", "", str(raw))
            if digits:
                candidate = int(digits)
                if 100 <= candidate <= 2000000:
                    result["mileage"] = candidate
        elif lowered in {"image", "images"}:
            values = raw if isinstance(raw, list) else [raw]
            for image in values:
                if isinstance(image, str) and image.startswith("http"):
                    result.setdefault("images", []).append(image)
                elif isinstance(image, dict):
                    image_url = image.get("url") or image.get("contentUrl")
                    if isinstance(image_url, str) and image_url.startswith("http"):
                        result.setdefault("images", []).append(image_url)
        _walk_json(raw, result)


def _structured_facts(structured_data: str) -> dict:
    result: dict = {"images": []}
    try:
        scripts = json.loads(structured_data or "[]")
    except (json.JSONDecodeError, TypeError):
        scripts = []
    if not isinstance(scripts, list):
        scripts = []
    for script in scripts[:30]:
        if not isinstance(script, str):
            continue
        try:
            parsed = json.loads(script)
        except json.JSONDecodeError:
            continue
        _walk_json(parsed, result)
    result["images"] = list(dict.fromkeys(result.get("images", [])))
    return result


def _bookmarklet(target: str) -> str:
    # Standard form POST avoids CORS: the browser navigates the captured data to Womo AI.
    js = r'''javascript:(()=>{try{const q=(s)=>document.querySelector(s);const meta=(p)=>q(`meta[property="${p}"]`)?.content||q(`meta[name="${p}"]`)?.content||'';const txt=(el)=>el?.innerText?.trim()||'';const desc=txt(q('[itemprop="description"]'))||txt(q('[data-testid*="description" i]'))||txt(q('[class*="description" i]'))||meta('og:description')||meta('description');const imgs=[meta('og:image'),...Array.from(document.images).filter(i=>(i.naturalWidth||i.width||0)>=280&&(i.naturalHeight||i.height||0)>=180).map(i=>i.currentSrc||i.src)].filter(Boolean).filter(u=>/^https?:/i.test(u));const ld=Array.from(document.querySelectorAll('script[type="application/ld+json"]')).slice(0,30).map(s=>s.textContent||'');const data={url:location.href,title:meta('og:title')||document.title||'',meta_description:meta('og:description')||meta('description')||'',description:desc,page_text:(document.body?.innerText||'').slice(0,120000),structured_data:JSON.stringify(ld),image_urls:JSON.stringify([...new Set(imgs)].slice(0,80))};const f=document.createElement('form');f.method='POST';f.action='__TARGET__';f.target='_self';for(const[k,v]of Object.entries(data)){const x=document.createElement('textarea');x.name=k;x.value=v;x.style.display='none';f.appendChild(x)}document.body.appendChild(f);f.submit()}catch(e){alert('Womo AI Capture: '+e.message)}})()'''
    return js.replace("__TARGET__", target)


@router.get("/capture/setup", response_class=HTMLResponse)
def capture_setup(request: Request):
    origin = str(request.base_url).rstrip("/")
    bookmarklet = _bookmarklet(f"{origin}/capture/import")
    return templates.TemplateResponse("capture_setup.html", {
        "request": request,
        "origin": origin,
        "bookmarklet": bookmarklet,
    })


@router.post("/capture/import")
def capture_import(
    url: str = Form(...),
    title: str = Form(""),
    meta_description: str = Form(""),
    description: str = Form(""),
    page_text: str = Form(""),
    structured_data: str = Form("[]"),
    image_urls: str = Form("[]"),
    db: Session = Depends(get_db),
):
    clean_url = _clean_url(url)
    if not clean_url:
        return RedirectResponse(url="/capture/setup?error=invalid_url", status_code=303)

    structured = _structured_facts(structured_data)
    combined_text = "\n\n".join(part for part in [title, description, meta_description, page_text] if part).strip()
    extracted = extract_listing_text(combined_text, current_title=title)

    if structured.get("price") is not None:
        extracted.setdefault("price", structured["price"])
    if structured.get("year") is not None:
        extracted.setdefault("year", structured["year"])
    if structured.get("mileage") is not None:
        extracted.setdefault("mileage", structured["mileage"])

    best_title = (title or structured.get("title") or "Noch nicht analysiert").strip()[:300]
    best_description = (description or structured.get("description") or meta_description or page_text[:12000]).strip()
    images = _safe_json_list(image_urls, 80)
    images.extend(structured.get("images", []))
    images = list(dict.fromkeys(url for url in images if url.startswith("http")))[:100]

    found = db.scalar(select(Listing).where(Listing.url == clean_url))
    payload = {
        "source": found.source if found else _source_from_url(clean_url),
        "url": clean_url,
        "title": best_title,
        "description": best_description,
        "status": "active",
        "image_urls": images,
        **extracted,
    }
    score_input = dict(payload)
    score, reasons = score_listing(score_input, SearchCriteria())
    payload["score"] = score
    payload["score_explanation"] = ", ".join(reasons)
    listing = upsert_listing(db, payload)

    snapshot = CaptureSnapshot(
        listing_id=listing.id,
        page_title=title[:2000],
        meta_description=meta_description[:10000],
        page_text=page_text[:120000],
        structured_data=structured_data[:120000],
        image_urls_json=json.dumps(images, ensure_ascii=False),
    )
    db.add(snapshot)

    state = listing.import_state
    if not state:
        state = ImportState(listing_id=listing.id)
        db.add(state)
    state.state = "captured"
    state.message = f"One-Tap Capture: Seitentext, strukturierte Daten und {len(images)} Bild-URLs übernommen."
    db.commit()

    return RedirectResponse(url=f"/listings/{listing.id}?captured=1", status_code=303)
