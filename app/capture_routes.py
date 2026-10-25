import json
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import CaptureSnapshot, ImportState, Listing, ListingImage, ListingSignals, VehicleIdentity
from .repository import upsert_listing
from .scoring import SearchCriteria, score_listing
from .text_enrichment import extract_listing_text, extract_vehicle_identity

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


def _safe_json_list(value: str, limit: int = 200) -> list[str]:
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


def _safe_json_dict(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
    for script in scripts[:40]:
        if not isinstance(script, str):
            continue
        try:
            parsed = json.loads(script)
        except json.JSONDecodeError:
            continue
        _walk_json(parsed, result)
    result["images"] = list(dict.fromkeys(result.get("images", [])))
    return result


def _mobile_image_score(url: str) -> int:
    value = url.lower()
    for size, score in (("mo-2000", 2000), ("mo-1600", 1600), ("mo-1280", 1280), ("mo-1024", 1024), ("mo-800", 800), ("mo-640", 640), ("mo-480", 480), ("mo-320", 320)):
        if size in value:
            return score
    numbers = [int(n) for n in re.findall(r"(?:w=|width=|/)(\d{3,4})(?:[&./-]|$)", value)]
    return max(numbers, default=500)


def _filter_portal_images(source: str, candidates: list[str]) -> list[str]:
    valid = []
    for url in candidates:
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        lower = url.lower()
        if re.search(r"(?:logo|avatar|icon|sprite|badge|banner|placeholder|tracking|pixel)", lower):
            continue
        valid.append(url)

    if source == "mobile.de":
        gallery = []
        for url in valid:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            path = parsed.path.lower()
            if "classistatic" in host and ("mo-prod/images" in path or "/images/" in path):
                gallery.append(url)
        if gallery:
            valid = gallery
        best_by_key: dict[str, tuple[int, str]] = {}
        for url in valid:
            parsed = urlparse(url)
            key = f"{parsed.netloc.lower()}{parsed.path}"
            score = _mobile_image_score(url)
            current = best_by_key.get(key)
            if current is None or score > current[0]:
                best_by_key[key] = (score, url)
        return [item[1] for item in best_by_key.values()]

    seen = set()
    result = []
    for url in valid:
        parsed = urlparse(url)
        key = f"{parsed.netloc.lower()}{parsed.path}"
        if key in seen:
            continue
        seen.add(key)
        result.append(url)
    return result


def _int_from_match(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text or "", re.I)
    if not match:
        return None
    digits = re.sub(r"[^0-9]", "", match.group(1))
    return int(digits) if digits else None


def _extract_signals(source: str, page_text: str, portal_data: dict, image_count: int) -> dict:
    text = page_text or ""
    data = {
        "portal_listing_id": portal_data.get("listing_id"),
        "listed_at_text": portal_data.get("listed_at"),
        "seller_name": portal_data.get("seller_name"),
        "seller_type": portal_data.get("seller_type"),
        "seller_active_since": portal_data.get("seller_active_since"),
        "seller_ads_online": portal_data.get("seller_ads_online"),
        "seller_ads_total": portal_data.get("seller_ads_total"),
        "seller_badges": portal_data.get("seller_badges"),
        "views": portal_data.get("views"),
        "watchers": portal_data.get("watchers"),
        "reported_image_count": portal_data.get("reported_image_count"),
        "dealer_name": portal_data.get("dealer_name"),
    }
    if source == "Kleinanzeigen":
        m = re.search(r"Aktiv seit\s+([^\n]+)", text, re.I)
        if m and not data["seller_active_since"]:
            data["seller_active_since"] = m.group(1).strip()[:80]
        if not data["seller_type"]:
            m = re.search(r"\b(Privater Nutzer|Gewerblicher Nutzer)\b", text, re.I)
            if m:
                data["seller_type"] = m.group(1)
        if data["seller_ads_online"] is None:
            data["seller_ads_online"] = _int_from_match(r"([\d.]+)\s+Anzeigen online", text)
        if data["seller_ads_total"] is None:
            data["seller_ads_total"] = _int_from_match(r"([\d.]+)\s+Anzeigen gesamt", text)
        if not data["portal_listing_id"]:
            m = re.search(r"Anzeigen-ID\s*([0-9]{6,})", text, re.I)
            if m:
                data["portal_listing_id"] = m.group(1)
        badges = []
        for badge in ("TOP Zufriedenheit", "Besonders freundlich", "Sehr freundlich", "Besonders zuverlässig", "Sehr zuverlässig"):
            if badge.lower() in text.lower():
                badges.append(badge)
        if badges and not data["seller_badges"]:
            data["seller_badges"] = ", ".join(badges)
    elif source == "Caraworld":
        if not data["portal_listing_id"]:
            m = re.search(r"Caraworld ID\s+([^\n]+)", text, re.I)
            if m:
                data["portal_listing_id"] = m.group(1).strip()[:120]
        if not data["dealer_name"]:
            m = re.search(r"(?:Anbieter|Händlerlogo)\s*\n?\s*([^\n]{2,100})", text, re.I)
            if m:
                data["dealer_name"] = m.group(1).strip()
        if data["reported_image_count"] is None:
            reported = _int_from_match(r"([0-9]{1,3})\s+Bilder", text)
            if reported:
                data["reported_image_count"] = reported
    raw = {k: v for k, v in data.items() if v not in (None, "")}
    data["raw_signal_text"] = json.dumps(raw, ensure_ascii=False)
    return data


def _bookmarklet(target: str) -> str:
    js = r'''javascript:(()=>{try{const q=(s)=>document.querySelector(s);const qa=(s)=>Array.from(document.querySelectorAll(s));const meta=(p)=>q(`meta[property="${p}"]`)?.content||q(`meta[name="${p}"]`)?.content||'';const txt=(el)=>el?.innerText?.trim()||'';const body=(document.body?.innerText||'');const host=location.hostname.toLowerCase();const abs=(u)=>{try{return new URL(u,location.href).href}catch{return''}};const urls=new Set();const add=(u)=>{u=abs((u||'').trim());if(/^https?:/i.test(u)&&!/(logo|avatar|icon|sprite|badge|banner|placeholder)/i.test(u))urls.add(u)};const srcset=(v)=>String(v||'').split(',').forEach(x=>add(x.trim().split(/\s+/)[0]));add(meta('og:image'));qa('img').forEach(i=>{add(i.currentSrc);add(i.src);['data-src','data-lazy-src','data-original','data-image','data-url'].forEach(a=>add(i.getAttribute(a)));srcset(i.srcset);srcset(i.getAttribute('data-srcset'))});qa('source').forEach(s=>{srcset(s.srcset);srcset(s.getAttribute('data-srcset'))});qa('link[rel="preload"][as="image"],link[rel="image_src"]').forEach(l=>add(l.href));qa('a[href]').forEach(a=>{/\.(jpe?g|png|webp)(\?|$)/i.test(a.href)&&add(a.href)});qa('[style*="background-image"]').forEach(e=>{const m=(e.style.backgroundImage||'').match(/url\(["']?(.*?)["']?\)/i);m&&add(m[1])});const ld=qa('script[type="application/ld+json"]').slice(0,40).map(s=>s.textContent||'');let desc=txt(q('[itemprop="description"]'))||txt(q('[data-testid*="description" i]'))||txt(q('[class*="description" i]'))||meta('og:description')||meta('description');const p={host};const pick=(r)=>{const m=body.match(r);return m?m[1].trim():''};const num=(v)=>{const n=parseInt(String(v||'').replace(/\D/g,''),10);return Number.isFinite(n)?n:null};if(host.includes('kleinanzeigen')){p.listing_id=pick(/Anzeigen-ID\s*([0-9]{6,})/i)||((location.pathname.match(/\/([0-9]{6,})-[0-9-]+\/?$/)||[])[1]||'');p.seller_active_since=pick(/Aktiv seit\s+([^\n]+)/i);p.seller_type=pick(/\b(Privater Nutzer|Gewerblicher Nutzer)\b/i);p.seller_ads_online=num(pick(/([\d.]+)\s+Anzeigen online/i));p.seller_ads_total=num(pick(/([\d.]+)\s+Anzeigen gesamt/i));const b=['TOP Zufriedenheit','Besonders freundlich','Sehr freundlich','Besonders zuverlässig','Sehr zuverlässig'].filter(x=>body.toLowerCase().includes(x.toLowerCase()));p.seller_badges=b.join(', ');const date=body.match(/(?:Nordrhein-Westfalen|Rheinland-Pfalz|Bayern|Hessen|Niedersachsen|Sachsen|Thüringen|Brandenburg|Berlin|Hamburg|Bremen|Saarland|Schleswig-Holstein|Baden-Württemberg|Mecklenburg-Vorpommern|Sachsen-Anhalt)[^\n]*\n([^\n]{3,30})/i);if(date)p.listed_at=date[1].trim()}else if(host.includes('caraworld')){p.listing_id=pick(/Caraworld ID\s+([^\n]+)/i);p.reported_image_count=num(pick(/([0-9]{1,3})\s+Bilder/i));const h=body.match(/(?:Anbieter|Händlerseite)\s*\n\s*([^\n]{2,100})/i);if(h)p.dealer_name=h[1].trim()}else if(host.includes('autoscout24')){p.listing_id=((location.pathname.match(/-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})/i)||[])[1]||'');const c=body.match(/(?:Bilder|Fotos)\s*[: ]\s*([0-9]{1,3})/i);if(c)p.reported_image_count=num(c[1])}else if(host.includes('mobile.de')){p.listing_id=(new URLSearchParams(location.search)).get('id')||'';const c=body.match(/(?:Bilder|Fotos)\s*[: ]\s*([0-9]{1,3})/i);if(c)p.reported_image_count=num(c[1])}let captured=[...urls];if(host.includes('mobile.de')){const m=captured.filter(u=>/classistatic/i.test(u)&&/mo-prod\/images/i.test(u));if(m.length)captured=m}const data={url:location.href,title:meta('og:title')||document.title||'',meta_description:meta('og:description')||meta('description')||'',description:desc,page_text:body.slice(0,150000),structured_data:JSON.stringify(ld),image_urls:JSON.stringify(captured.slice(0,180)),portal_data:JSON.stringify(p)};const f=document.createElement('form');f.method='POST';f.action='__TARGET__';f.target='_self';for(const[k,v]of Object.entries(data)){const x=document.createElement('textarea');x.name=k;x.value=v;x.style.display='none';f.appendChild(x)}document.body.appendChild(f);f.submit()}catch(e){alert('Womo AI Capture: '+e.message)}})()'''
    return js.replace("__TARGET__", target)


@router.get("/capture/setup", response_class=HTMLResponse)
def capture_setup(request: Request):
    origin = str(request.base_url).rstrip("/")
    bookmarklet = _bookmarklet(f"{origin}/capture/import")
    return templates.TemplateResponse("capture_setup.html", {
        "request": request,
        "origin": origin,
        "bookmarklet": bookmarklet,
        "error": request.query_params.get("error"),
    })


@router.get("/capture/import")
def capture_import_get():
    return RedirectResponse(url="/capture/setup?error=stale_bookmarklet", status_code=303)


@router.post("/capture/import")
def capture_import(
    url: str = Form(...),
    title: str = Form(""),
    meta_description: str = Form(""),
    description: str = Form(""),
    page_text: str = Form(""),
    structured_data: str = Form("[]"),
    image_urls: str = Form("[]"),
    portal_data: str = Form("{}"),
    db: Session = Depends(get_db),
):
    clean_url = _clean_url(url)
    if not clean_url:
        return RedirectResponse(url="/capture/setup?error=invalid_url", status_code=303)

    source = _source_from_url(clean_url)
    structured = _structured_facts(structured_data)
    portal = _safe_json_dict(portal_data)
    best_title = (title or structured.get("title") or "Noch nicht analysiert").strip()[:300]
    best_description = (description or structured.get("description") or meta_description or "").strip()

    primary_text = "\n\n".join(part for part in [best_description, meta_description] if part).strip()
    extracted = extract_listing_text(primary_text, current_title=best_title)
    fallback = extract_listing_text(page_text[:35000], current_title=best_title)
    for key in ("price", "year", "mileage", "power_kw", "weight_kg", "seats", "body_type", "three_point_belt", "dry_status", "repair_level"):
        if key not in extracted and key in fallback:
            extracted[key] = fallback[key]

    for key in ("price", "year", "mileage"):
        if structured.get(key) is not None:
            extracted[key] = structured[key]

    identity = extract_vehicle_identity(primary_text=primary_text, current_title=best_title, fallback_text=page_text[:35000])
    if identity.get("engine"):
        extracted["engine"] = identity["engine"]
    if identity.get("coachbuilder"):
        extracted["make"] = identity["coachbuilder"]
    elif identity.get("base_make"):
        extracted["make"] = identity["base_make"]
    if identity.get("coach_model"):
        extracted.setdefault("model", identity["coach_model"])

    if not best_description:
        best_description = (structured.get("description") or page_text[:12000]).strip()

    candidates = _safe_json_list(image_urls, 200)
    candidates.extend(structured.get("images", []))
    images = _filter_portal_images(source, list(dict.fromkeys(candidates)))[:100]

    found = db.scalar(select(Listing).where(Listing.url == clean_url))
    payload = {
        "source": found.source if found else source,
        "url": clean_url,
        "title": best_title,
        "description": best_description,
        "status": "active",
        "image_urls": images,
        **extracted,
    }
    score, reasons = score_listing(dict(payload), SearchCriteria())
    payload["score"] = score
    payload["score_explanation"] = ", ".join(reasons)
    listing = upsert_listing(db, payload)

    image_set = set(images)
    for image in list(listing.images):
        if image.remote_url not in image_set:
            db.delete(image)
    existing_urls = {img.remote_url for img in listing.images if img.remote_url in image_set}
    for index, image_url in enumerate(images):
        if image_url not in existing_urls:
            db.add(ListingImage(listing_id=listing.id, remote_url=image_url, sort_order=index))

    vehicle = db.scalar(select(VehicleIdentity).where(VehicleIdentity.listing_id == listing.id))
    if not vehicle:
        vehicle = VehicleIdentity(listing_id=listing.id)
        db.add(vehicle)
    vehicle.base_make = identity.get("base_make")
    vehicle.base_model = identity.get("base_model")
    vehicle.coachbuilder = identity.get("coachbuilder")
    vehicle.coach_model = identity.get("coach_model")
    vehicle.engine_text = identity.get("engine")

    signal_values = _extract_signals(source, page_text, portal, len(images))
    signals = db.scalar(select(ListingSignals).where(ListingSignals.listing_id == listing.id))
    if not signals:
        signals = ListingSignals(listing_id=listing.id)
        db.add(signals)
    for key, value in signal_values.items():
        if value not in (None, ""):
            setattr(signals, key, value)

    db.add(CaptureSnapshot(
        listing_id=listing.id,
        page_title=title[:2000],
        meta_description=meta_description[:10000],
        page_text=page_text[:120000],
        structured_data=structured_data[:120000],
        image_urls_json=json.dumps(images, ensure_ascii=False),
    ))

    state = listing.import_state
    if not state:
        state = ImportState(listing_id=listing.id)
        db.add(state)
    reported = signals.reported_image_count
    state.state = "captured"
    state.message = f"One-Tap Capture: {len(images)} Fahrzeugbilder übernommen"
    if reported and reported > len(images):
        state.message += f"; Portal meldet {reported} Bilder – {reported-len(images)} fehlen noch."
    else:
        state.message += "."
    db.commit()

    return RedirectResponse(url=f"/listings/{listing.id}?captured=1", status_code=303)
