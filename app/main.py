from math import ceil
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from .collectors.autoscout24 import AutoScout24Collector
from .collectors.mobile_de import MobileDeCollector
from .data import LISTINGS
from .database import Base, engine, get_db
from .models import Listing
from .repository import upsert_listing
from .scoring import SearchCriteria, matches_hard_filters, score_listing
from .search_intent import criteria_from_prompt

app = FastAPI(title="Womo AI", version="0.2.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
Base.metadata.create_all(bind=engine)


def listing_dict(row: Listing) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "source_id": row.source_id,
        "url": row.url,
        "title": row.title,
        "description": row.description,
        "price": row.price,
        "year": row.year,
        "mileage": row.mileage,
        "distance_km": row.distance_km,
        "location": row.location,
        "make": row.make,
        "model": row.model,
        "body_type": row.body_type,
        "engine": row.engine,
        "power_kw": row.power_kw,
        "seats": row.seats,
        "weight_kg": row.weight_kg,
        "three_point_belt": row.three_point_belt,
        "dry_status": row.dry_status,
        "repair_level": row.repair_level,
        "status": row.status,
        "images": [img.remote_url for img in row.images],
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
    }


def seed_once(db: Session):
    if (db.scalar(select(func.count()).select_from(Listing)) or 0) > 0:
        return
    for item in LISTINGS:
        data = dict(item)
        data["url"] = f"seed://{item['id']}"
        data["source_id"] = f"seed-{item['id']}"
        score, reasons = score_listing(data, SearchCriteria())
        data["score"] = score
        data["score_explanation"] = ", ".join(reasons)
        upsert_listing(db, data)


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


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    seed_once(db)
    return templates.TemplateResponse("index.html", {"request": request, "defaults": SearchCriteria()})


@app.get("/search", response_class=HTMLResponse)
def search_get(
    request: Request,
    prompt: str = Query(""),
    sort: str = Query("score"),
    direction: str = Query("desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100),
    status: str = Query("all"),
    db: Session = Depends(get_db),
):
    seed_once(db)
    criteria = criteria_from_prompt(prompt, SearchCriteria())
    return render_results(request, db, criteria, prompt, sort, direction, page, per_page, status)


@app.post("/search", response_class=HTMLResponse)
def search_post(
    request: Request,
    prompt: str = Form(""),
    max_price: int = Form(11000),
    max_distance_km: int = Form(300),
    min_year: int = Form(1988),
    max_mileage: int = Form(260000),
    require_three_point_belt: bool = Form(False),
    max_weight_kg: int = Form(3500),
    repair_tolerance: str = Form("medium"),
    preferred_engine: str = Form("2.5 TD"),
    require_alkoven: bool = Form(False),
    per_page: int = Form(20),
    db: Session = Depends(get_db),
):
    seed_once(db)
    criteria = SearchCriteria(
        max_price=max_price,
        max_distance_km=max_distance_km,
        min_year=min_year,
        max_mileage=max_mileage,
        require_three_point_belt=require_three_point_belt,
        max_weight_kg=max_weight_kg,
        repair_tolerance=repair_tolerance,
        preferred_engine=preferred_engine.strip(),
        require_alkoven=require_alkoven,
    )
    if prompt.strip():
        criteria = criteria_from_prompt(prompt, criteria)
    return render_results(request, db, criteria, prompt, "score", "desc", 1, per_page, "all")


def render_results(request, db, criteria, prompt, sort, direction, page, per_page, status):
    rows = db.scalars(select(Listing)).all()
    results = []
    for row in rows:
        item = listing_dict(row)
        if status != "all" and item["status"] != status:
            continue
        if not matches_hard_filters(item, criteria):
            continue
        score, reasons = score_listing(item, criteria)
        item["score"] = score
        item["score_reasons"] = reasons
        results.append(item)

    allowed_sort = {"score", "price", "distance_km", "year", "mileage", "first_seen_at", "last_seen_at"}
    sort = sort if sort in allowed_sort else "score"
    reverse = direction != "asc"
    def sort_key(item):
        value = item.get(sort)
        if value is None:
            return float("-inf") if reverse else float("inf")
        return value
    results.sort(key=sort_key, reverse=reverse)

    total = len(results)
    pages = max(1, ceil(total / per_page))
    page = min(page, pages)
    start = (page - 1) * per_page
    visible = results[start:start + per_page]

    return templates.TemplateResponse("results.html", {
        "request": request,
        "criteria": criteria,
        "prompt": prompt,
        "results": visible,
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "sort": sort,
        "direction": direction,
        "status": status,
    })


@app.post("/listings/manual")
def add_manual_listing(
    url: str = Form(...),
    title: str = Form("Noch nicht analysiert"),
    description: str = Form(""),
    price: int | None = Form(None),
    db: Session = Depends(get_db),
):
    source = detect_source(url)
    upsert_listing(db, {
        "source": source,
        "url": url.strip(),
        "title": title.strip() or "Noch nicht analysiert",
        "description": description.strip(),
        "price": price,
        "status": "active",
    })
    return RedirectResponse(url="/search?sort=first_seen_at&direction=desc", status_code=303)


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
        detail["score"] = score
        detail["score_explanation"] = ", ".join(reasons)
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
    return {"status": "ok", "version": "0.2.0"}
