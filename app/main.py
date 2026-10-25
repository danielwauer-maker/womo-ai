from math import ceil
import re
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .capture_routes import router as capture_router
from .collectors.autoscout24 import AutoScout24Collector
from .collectors.mobile_de import MobileDeCollector
from .database import Base, engine, get_db
from .detail_routes import router as detail_router
from .importer import process_listing
from .models import Listing
from .repository import upsert_listing
from .review_routes import router as review_router
from .scoring import SearchCriteria, assess_listing, matches_hard_filters, score_listing
from .search_intent import criteria_from_prompt
from .technical_data import loads_technical_data

app = FastAPI(title="Womo AI", version="0.9.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(detail_router)
app.include_router(capture_router)
app.include_router(review_router)
templates = Jinja2Templates(directory="app/templates")
Base.metadata.create_all(bind=engine)

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def listing_dict(row: Listing) -> dict:
    identity = row.vehicle_identity
    technical = loads_technical_data(row.technical_data.data_json) if row.technical_data else {}
    return {
        "id": row.id, "source": row.source, "source_id": row.source_id, "url": row.url,
        "title": row.title, "description": row.description, "price": row.price, "year": row.year,
        "mileage": row.mileage, "distance_km": row.distance_km, "location": row.location,
        "make": row.make, "model": row.model, "body_type": row.body_type, "engine": row.engine,
        "engine_text": identity.engine_text if identity else row.engine,
        "base_make": identity.base_make if identity else None,
        "base_model": identity.base_model if identity else None,
        "coachbuilder": identity.coachbuilder if identity else None,
        "coach_model": identity.coach_model if identity else None,
        "technical": technical,
        "power_kw": row.power_kw, "seats": row.seats, "weight_kg": row.weight_kg,
        "three_point_belt": row.three_point_belt, "dry_status": row.dry_status,
        "repair_level": row.repair_level, "status": row.status,
        "images": [img.remote_url for img in row.images],
        "first_seen_at": row.first_seen_at, "last_seen_at": row.last_seen_at,
        "import_state": row.import_state.state if row.import_state else "ready",
        "import_message": row.import_state.message if row.import_state else "",
    }


def cleanup_test_data(db: Session) -> None:
    rows = db.scalars(select(Listing).where(Listing.url.like("seed://%"))).all()
    if rows:
        for row in rows:
            db.delete(row)
        db.commit()


def detect_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "kleinanzeigen" in host:
        return "Kleinanzeigen"
    if "mobile.de" in host:
        return "mobile.de"
    if "autoscout24" in host:
        return "AutoScout24"
    if "caraworld" in host:
        return "Caraworld"
    return host.replace("www.", "") or "manual"


def normalize_url(url: str) -> str:
    url = url.strip().rstrip(".,;)")
    parsed = urlparse(url)
    return url if parsed.scheme and parsed.netloc else ""


def extract_urls(text: str) -> list[str]:
    seen, urls = set(), []
    for match in URL_RE.findall(text or ""):
        url = normalize_url(match)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def import_urls(db: Session, urls: list[str]) -> tuple[int, int, int, int]:
    created = existing = extracted = awaiting = 0
    for url in urls:
        found = db.scalar(select(Listing).where(Listing.url == url))
        if found:
            existing += 1
            listing = upsert_listing(db, {"source": found.source, "url": url, "status": "active"})
        else:
            listing = upsert_listing(db, {
                "source": detect_source(url), "url": url, "title": "Noch nicht analysiert",
                "description": "", "status": "active",
            })
            created += 1
        state = process_listing(db, listing)
        if state.state == "extracted":
            extracted += 1
        elif state.state in {"awaiting_details", "failed"}:
            awaiting += 1
    return created, existing, extracted, awaiting


@app.get("/", response_class=HTMLResponse)
def home(request: Request, imported: int = Query(0), existing: int = Query(0), invalid: int = Query(0),
         extracted: int = Query(0), awaiting: int = Query(0), db: Session = Depends(get_db)):
    cleanup_test_data(db)
    return templates.TemplateResponse("index.html", {
        "request": request, "defaults": SearchCriteria(), "imported": imported,
        "existing": existing, "invalid": invalid, "extracted": extracted, "awaiting": awaiting,
    })


@app.get("/share", response_class=HTMLResponse)
def share_receiver(request: Request, title: str = Query(""), text: str = Query(""), url: str = Query(""),
                   db: Session = Depends(get_db)):
    cleanup_test_data(db)
    candidates = extract_urls("\n".join([url, text]))
    shared_url = candidates[0] if candidates else ""
    existing = db.scalar(select(Listing).where(Listing.url == shared_url)) if shared_url else None
    return templates.TemplateResponse("share.html", {
        "request": request, "shared_url": shared_url, "shared_title": title.strip(),
        "shared_text": text.strip(), "existing": listing_dict(existing) if existing else None,
    })


@app.post("/share/import")
def share_import(url: str = Form(...), title: str = Form(""), text: str = Form(""), db: Session = Depends(get_db)):
    clean_url = normalize_url(url)
    if not clean_url:
        return RedirectResponse(url="/share", status_code=303)
    found = db.scalar(select(Listing).where(Listing.url == clean_url))
    if found:
        listing = upsert_listing(db, {"source": found.source, "url": clean_url, "status": "active"})
    else:
        listing = upsert_listing(db, {
            "source": detect_source(clean_url), "url": clean_url,
            "title": title.strip() or "Noch nicht analysiert", "description": text.strip(), "status": "active",
        })
    process_listing(db, listing)
    return RedirectResponse(url=f"/listings/{listing.id}", status_code=303)


@app.get("/archive", response_class=HTMLResponse)
def archive(
    request: Request,
    source: str = Query("all"), state: str = Query("all"), status: str = Query("all"),
    postal_code: str = Query(""), max_distance_km: int | None = Query(None, ge=0, le=1000),
    min_price: int | None = Query(None, ge=0), max_price: int | None = Query(None, ge=0),
    min_score: int | None = Query(None, ge=0, le=100), verdict: str = Query("all"),
    sort: str = Query("score_desc"), page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=100), db: Session = Depends(get_db)
):
    cleanup_test_data(db)
    rows = db.scalars(select(Listing).order_by(Listing.first_seen_at.desc())).all()
    criteria = SearchCriteria()
    filtered = []
    verdicts = {"sehr interessant", "interessant", "mit Vorbehalt", "kritisch prüfen", "eher nicht passend", "zu wenig Daten"}

    for row in rows:
        item = listing_dict(row)
        assessment = assess_listing(item, criteria)
        item["assessment"] = assessment
        item["score"] = assessment["score"]
        item["verdict"] = assessment["verdict"]
        item["confidence"] = assessment["confidence"]

        if source != "all" and item["source"] != source:
            continue
        if state != "all" and item["import_state"] != state:
            continue
        if status != "all" and item["status"] != status:
            continue
        if min_price is not None and (item["price"] is None or item["price"] < min_price):
            continue
        if max_price is not None and (item["price"] is None or item["price"] > max_price):
            continue
        if min_score is not None and item["score"] < min_score:
            continue
        if verdict != "all" and verdict in verdicts and item["verdict"] != verdict:
            continue
        if max_distance_km is not None and (item["distance_km"] is None or item["distance_km"] > max_distance_km):
            continue
        filtered.append(item)

    if sort == "score_asc":
        filtered.sort(key=lambda x: (x.get("score") is None, x.get("score") if x.get("score") is not None else 101))
    elif sort == "price_asc":
        filtered.sort(key=lambda x: (x.get("price") is None, x.get("price") if x.get("price") is not None else float("inf")))
    elif sort == "price_desc":
        filtered.sort(key=lambda x: (x.get("price") is not None, x.get("price") or -1), reverse=True)
    elif sort == "distance_asc":
        filtered.sort(key=lambda x: (x.get("distance_km") is None, x.get("distance_km") if x.get("distance_km") is not None else float("inf")))
    elif sort == "newest":
        filtered.sort(key=lambda x: (x.get("first_seen_at") is not None, x.get("first_seen_at")), reverse=True)
    else:
        sort = "score_desc"
        filtered.sort(key=lambda x: (x.get("score") is not None, x.get("score") or -1), reverse=True)

    total = len(filtered)
    pages = max(1, ceil(total / per_page))
    page = min(page, pages)
    visible = filtered[(page - 1) * per_page:page * per_page]
    sources = sorted({row.source for row in rows if row.source})
    return templates.TemplateResponse("archive.html", {
        "request": request, "items": visible, "total": total, "page": page, "pages": pages,
        "per_page": per_page, "source": source, "state": state, "status": status, "sources": sources,
        "postal_code": postal_code, "max_distance_km": max_distance_km,
        "min_price": min_price, "max_price": max_price, "min_score": min_score,
        "verdict": verdict, "sort": sort,
    })


@app.get("/search", response_class=HTMLResponse)
def search_get(request: Request, prompt: str = Query(""), sort: str = Query("score"), direction: str = Query("desc"),
               page: int = Query(1, ge=1), per_page: int = Query(20, ge=5, le=100), status: str = Query("all"),
               db: Session = Depends(get_db)):
    cleanup_test_data(db)
    return render_results(request, db, criteria_from_prompt(prompt, SearchCriteria()), prompt, sort, direction, page, per_page, status)


@app.post("/search", response_class=HTMLResponse)
def search_post(request: Request, prompt: str = Form(""), max_price: int = Form(11000),
                max_distance_km: int = Form(300), min_year: int = Form(1988), max_mileage: int = Form(260000),
                require_three_point_belt: bool = Form(False), max_weight_kg: int = Form(3500),
                repair_tolerance: str = Form("medium"), preferred_engine: str = Form("2.5 TD"),
                require_alkoven: bool = Form(False), per_page: int = Form(20), db: Session = Depends(get_db)):
    cleanup_test_data(db)
    criteria = SearchCriteria(max_price=max_price, max_distance_km=max_distance_km, min_year=min_year,
                              max_mileage=max_mileage, require_three_point_belt=require_three_point_belt,
                              max_weight_kg=max_weight_kg, repair_tolerance=repair_tolerance,
                              preferred_engine=preferred_engine.strip(), require_alkoven=require_alkoven)
    if prompt.strip():
        criteria = criteria_from_prompt(prompt, criteria)
    return render_results(request, db, criteria, prompt, "score", "desc", 1, per_page, "all")


def render_results(request, db, criteria, prompt, sort, direction, page, per_page, status):
    results = []
    for row in db.scalars(select(Listing)).all():
        item = listing_dict(row)
        if status != "all" and item["status"] != status:
            continue
        if not matches_hard_filters(item, criteria):
            continue
        score, reasons = score_listing(item, criteria)
        item["score"], item["score_reasons"] = score, reasons
        results.append(item)
    allowed_sort = {"score", "price", "distance_km", "year", "mileage", "first_seen_at", "last_seen_at"}
    sort = sort if sort in allowed_sort else "score"
    reverse = direction != "asc"
    def sort_key(item):
        value = item.get(sort)
        return (float("-inf") if reverse else float("inf")) if value is None else value
    results.sort(key=sort_key, reverse=reverse)
    total = len(results)
    pages = max(1, ceil(total / per_page))
    page = min(page, pages)
    visible = results[(page - 1) * per_page:page * per_page]
    return templates.TemplateResponse("results.html", {
        "request": request, "criteria": criteria, "prompt": prompt, "results": visible, "total": total,
        "page": page, "pages": pages, "per_page": per_page, "sort": sort, "direction": direction, "status": status,
    })


@app.post("/listings/manual")
def add_manual_listing(url: str = Form(...), title: str = Form("Noch nicht analysiert"),
                       description: str = Form(""), price: int | None = Form(None), db: Session = Depends(get_db)):
    listing = upsert_listing(db, {
        "source": detect_source(url), "url": normalize_url(url), "title": title.strip() or "Noch nicht analysiert",
        "description": description.strip(), "price": price, "status": "active",
    })
    process_listing(db, listing)
    return RedirectResponse(url=f"/listings/{listing.id}", status_code=303)


@app.post("/listings/batch")
async def add_batch_listings(urls_text: str = Form(""), file: UploadFile | None = File(None), db: Session = Depends(get_db)):
    combined, invalid = urls_text or "", 0
    if file and file.filename:
        raw = await file.read()
        try:
            combined += "\n" + raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                combined += "\n" + raw.decode("latin-1")
            except UnicodeDecodeError:
                invalid += 1
    urls = extract_urls(combined)
    raw_candidates = [line.strip() for line in combined.splitlines() if line.strip()]
    invalid += max(0, len(raw_candidates) - len(urls))
    created, existing, extracted, awaiting = import_urls(db, urls)
    return RedirectResponse(url=f"/?imported={created}&existing={existing}&invalid={invalid}&extracted={extracted}&awaiting={awaiting}#batch-import", status_code=303)


@app.post("/listings/{listing_id}/reprocess")
def reprocess_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if listing:
        process_listing(db, listing)
    return RedirectResponse(url=f"/listings/{listing_id}", status_code=303)


@app.post("/sync/mobile")
def sync_mobile(db: Session = Depends(get_db)):
    collector = MobileDeCollector()
    if not collector.configured:
        return RedirectResponse(url="/search?source_error=mobile_not_configured", status_code=303)
    criteria = SearchCriteria()
    for data in collector.search(criteria, page=1, page_size=100):
        detail = data
        if data.get("source_id"):
            try:
                detail = collector.fetch_detail(data["source_id"])
            except Exception:
                pass
        score, reasons = score_listing(detail, criteria)
        detail["score"], detail["score_explanation"] = score, ", ".join(reasons)
        upsert_listing(db, detail)
    return RedirectResponse(url="/search?sort=score&direction=desc", status_code=303)


@app.get("/sources")
def source_status():
    return {
        "mobile.de": {"configured": MobileDeCollector().configured},
        "AutoScout24": {"configured": AutoScout24Collector().configured, "note": "GraphQL schema mapping requires activated Search API account"},
        "manual": {"configured": True},
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.9.0"}
