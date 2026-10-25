from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .capture_routes import router as capture_router
from .database import get_db
from .models import Listing, VehicleIdentity
from .repository import upsert_listing
from .scoring import SearchCriteria, score_listing
from .text_enrichment import extract_listing_text, extract_vehicle_identity

router = APIRouter()
router.include_router(capture_router)
templates = Jinja2Templates(directory="app/templates")


def _to_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


@router.get("/listings/{listing_id}", response_class=HTMLResponse)
def listing_detail(request: Request, listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        return RedirectResponse(url="/archive", status_code=303)

    identity = listing.vehicle_identity
    signals = listing.signals
    captured_images = len(listing.images)
    reported_images = signals.reported_image_count if signals else None
    missing_images = max(0, (reported_images or captured_images) - captured_images)

    data = {
        "id": listing.id,
        "source": listing.source,
        "url": listing.url,
        "title": listing.title,
        "description": listing.description,
        "price": listing.price,
        "year": listing.year,
        "mileage": listing.mileage,
        "location": listing.location,
        "make": listing.make,
        "model": listing.model,
        "body_type": listing.body_type,
        "engine": listing.engine,
        "power_kw": listing.power_kw,
        "seats": listing.seats,
        "weight_kg": listing.weight_kg,
        "three_point_belt": listing.three_point_belt,
        "dry_status": listing.dry_status,
        "repair_level": listing.repair_level,
        "status": listing.status,
        "base_make": identity.base_make if identity else None,
        "base_model": identity.base_model if identity else None,
        "coachbuilder": identity.coachbuilder if identity else None,
        "coach_model": identity.coach_model if identity else None,
        "engine_text": identity.engine_text if identity else listing.engine,
        "images": [img.remote_url for img in listing.images],
        "reported_image_count": reported_images,
        "missing_image_count": missing_images,
        "portal_listing_id": signals.portal_listing_id if signals else None,
        "listed_at_text": signals.listed_at_text if signals else None,
        "seller_name": signals.seller_name if signals else None,
        "seller_type": signals.seller_type if signals else None,
        "seller_active_since": signals.seller_active_since if signals else None,
        "seller_ads_online": signals.seller_ads_online if signals else None,
        "seller_ads_total": signals.seller_ads_total if signals else None,
        "seller_badges": signals.seller_badges if signals else None,
        "views": signals.views if signals else None,
        "watchers": signals.watchers if signals else None,
        "dealer_name": signals.dealer_name if signals else None,
        "prices": sorted(listing.prices, key=lambda x: x.observed_at, reverse=True),
        "capture_count": len(listing.captures),
        "last_capture_at": max((capture.captured_at for capture in listing.captures), default=None),
        "import_state": listing.import_state.state if listing.import_state else "ready",
        "import_message": listing.import_state.message if listing.import_state else "",
    }
    score, reasons = score_listing(data, SearchCriteria())
    data["score"] = score
    data["score_reasons"] = reasons
    return templates.TemplateResponse("listing_detail.html", {"request": request, "item": data})


@router.post("/listings/{listing_id}/enrich")
def enrich_listing(
    listing_id: int,
    raw_text: str = Form(""),
    title: str = Form(""),
    price: str = Form(""),
    year: str = Form(""),
    mileage: str = Form(""),
    location: str = Form(""),
    base_make: str = Form(""),
    base_model: str = Form(""),
    coachbuilder: str = Form(""),
    coach_model: str = Form(""),
    body_type: str = Form(""),
    engine: str = Form(""),
    power_kw: str = Form(""),
    seats: str = Form(""),
    weight_kg: str = Form(""),
    three_point_belt: str = Form("unknown"),
    dry_status: str = Form("unknown"),
    repair_level: str = Form("unknown"),
    db: Session = Depends(get_db),
):
    listing = db.get(Listing, listing_id)
    if not listing:
        return RedirectResponse(url="/archive", status_code=303)

    extracted = extract_listing_text(raw_text, current_title=title or listing.title)
    identity_auto = extract_vehicle_identity(raw_text, current_title=title or listing.title)

    manual = {
        "source": listing.source,
        "url": listing.url,
        "title": title.strip() or listing.title,
        "description": raw_text.strip() or listing.description,
        "price": _to_int(price),
        "year": _to_int(year),
        "mileage": _to_int(mileage),
        "location": location.strip() or None,
        "make": coachbuilder.strip() or base_make.strip() or None,
        "model": coach_model.strip() or None,
        "body_type": body_type.strip() or None,
        "engine": engine.strip() or None,
        "power_kw": _to_int(power_kw),
        "seats": _to_int(seats),
        "weight_kg": _to_int(weight_kg),
        "three_point_belt": True if three_point_belt == "yes" else False if three_point_belt == "no" else None,
        "dry_status": dry_status if dry_status in {"unknown", "claimed_dry", "measured_dry"} else "unknown",
        "repair_level": repair_level if repair_level in {"unknown", "light", "medium", "heavy"} else "unknown",
        "status": listing.status,
    }

    merged = dict(extracted)
    for key, value in manual.items():
        if value not in (None, ""):
            merged[key] = value

    score, reasons = score_listing(merged, SearchCriteria())
    merged["score"] = score
    merged["score_explanation"] = ", ".join(reasons)
    upsert_listing(db, merged)

    vehicle = db.scalar(select(VehicleIdentity).where(VehicleIdentity.listing_id == listing_id))
    if not vehicle:
        vehicle = VehicleIdentity(listing_id=listing_id)
        db.add(vehicle)
    vehicle.base_make = base_make.strip() or identity_auto.get("base_make")
    vehicle.base_model = base_model.strip() or identity_auto.get("base_model")
    vehicle.coachbuilder = coachbuilder.strip() or identity_auto.get("coachbuilder")
    vehicle.coach_model = coach_model.strip() or identity_auto.get("coach_model")
    vehicle.engine_text = engine.strip() or identity_auto.get("engine") or listing.engine

    if listing.import_state:
        listing.import_state.state = "enriched"
        listing.import_state.message = "Inseratstext wurde übernommen und strukturiert ausgewertet."
    db.commit()

    return RedirectResponse(url=f"/listings/{listing_id}", status_code=303)
