import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .extractors import extract_snapshot
from .models import Listing, ListingImage, ListingSignals, ListingTechnicalData, VehicleIdentity
from .repository import upsert_listing
from .review_quality import quality_report
from .scoring import SearchCriteria, score_listing
from .technical_data import dumps_technical_data, extract_technical_data, loads_technical_data

router = APIRouter(prefix="/api/review", tags=["review"])


def _technical_scope(listing: Listing, latest_capture) -> str:
    # Kleinanzeigen pages contain lots of recommendations/UI text; seller description
    # is the authoritative semantic scope. Structured portals can safely use page text.
    if listing.source == "Kleinanzeigen":
        return listing.description or ""
    return "\n".join([
        listing.description or "",
        latest_capture.page_text if latest_capture else "",
    ])


def _review_payload(listing: Listing) -> dict:
    identity = listing.vehicle_identity
    signals = listing.signals
    latest_capture = max(listing.captures, key=lambda c: c.captured_at) if listing.captures else None
    technical = loads_technical_data(listing.technical_data.data_json) if listing.technical_data else {}
    if latest_capture:
        live_technical = extract_technical_data(_technical_scope(listing, latest_capture))
        # Fresh parser output is authoritative over previously persisted extraction.
        technical = {**technical, **live_technical}

    data = {
        "id": listing.id,
        "source": listing.source,
        "original_url": listing.url,
        "title": listing.title,
        "description": listing.description,
        "price": listing.price,
        "year": listing.year,
        "mileage": listing.mileage,
        "location": listing.location,
        "body_type": listing.body_type,
        "engine": identity.engine_text if identity and identity.engine_text else listing.engine,
        "power_kw": listing.power_kw,
        "seats": listing.seats,
        "weight_kg": listing.weight_kg,
        "three_point_belt": listing.three_point_belt,
        "dry_status": listing.dry_status,
        "repair_level": listing.repair_level,
        "score": listing.score,
        "base_make": identity.base_make if identity else None,
        "base_model": identity.base_model if identity else None,
        "coachbuilder": identity.coachbuilder if identity else None,
        "coach_model": identity.coach_model if identity else None,
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
        "images": [img.remote_url for img in listing.images],
        "capture_count": len(listing.captures),
        "last_capture_at": latest_capture.captured_at.isoformat() if latest_capture else None,
        "review_status": "unverified",
        "technical": technical,
    }
    data["quality"] = quality_report(data)
    if latest_capture:
        data["capture_snapshot"] = {
            "page_title": latest_capture.page_title,
            "meta_description": latest_capture.meta_description,
            "captured_at": latest_capture.captured_at.isoformat(),
            "page_text": latest_capture.page_text,
            "structured_data": latest_capture.structured_data,
            "image_urls": json.loads(latest_capture.image_urls_json or "[]"),
        }
    return data


@router.get("/pending")
def pending_review(db: Session = Depends(get_db)):
    listings = db.scalars(select(Listing).order_by(Listing.updated_at.desc())).all()
    return {
        "count": len(listings),
        "items": [
            {
                "id": row.id,
                "source": row.source,
                "title": row.title,
                "original_url": row.url,
                "quality": quality_report(_review_payload(row))["score"],
                "capture_count": len(row.captures),
            }
            for row in listings
        ],
    }


@router.get("/listings/{listing_id}")
def review_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return JSONResponse(_review_payload(listing))


@router.post("/listings/{listing_id}/reprocess")
def reprocess_snapshot(listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if not listing.captures:
        raise HTTPException(status_code=409, detail="No capture snapshot available")

    snapshot = max(listing.captures, key=lambda c: c.captured_at)
    result = extract_snapshot(
        listing.source,
        title=snapshot.page_title or listing.title,
        description=listing.description,
        page_text=snapshot.page_text,
        structured_data=snapshot.structured_data,
        image_urls_json=snapshot.image_urls_json,
    )

    payload = {
        "source": listing.source,
        "url": listing.url,
        "title": listing.title,
        "description": listing.description,
        "status": listing.status,
        **result.fields,
    }
    score, reasons = score_listing(payload, SearchCriteria())
    payload["score"] = score
    payload["score_explanation"] = ", ".join(reasons)
    upsert_listing(db, payload)

    # Reprocess means "rebuild parser-owned values from the stored snapshot".
    # Explicitly replace stale values instead of only filling blanks.
    replaceable_fields = (
        "price", "year", "mileage", "body_type", "engine", "power_kw",
        "seats", "weight_kg", "three_point_belt", "dry_status", "repair_level",
    )
    for key in replaceable_fields:
        setattr(listing, key, result.fields.get(key))
    if listing.dry_status is None:
        listing.dry_status = "unknown"
    if listing.repair_level is None:
        listing.repair_level = "unknown"

    identity = db.scalar(select(VehicleIdentity).where(VehicleIdentity.listing_id == listing.id))
    if not identity:
        identity = VehicleIdentity(listing_id=listing.id)
        db.add(identity)
    identity.base_make = result.identity.get("base_make")
    identity.base_model = result.identity.get("base_model")
    identity.coachbuilder = result.identity.get("coachbuilder")
    identity.coach_model = result.identity.get("coach_model")
    identity.engine_text = result.identity.get("engine")

    for image in list(listing.images):
        db.delete(image)
    for index, url in enumerate(result.images):
        db.add(ListingImage(listing_id=listing.id, remote_url=url, sort_order=index))

    signals = db.scalar(select(ListingSignals).where(ListingSignals.listing_id == listing.id))
    if not signals:
        signals = ListingSignals(listing_id=listing.id)
        db.add(signals)
    signal_fields = (
        "portal_listing_id", "listed_at_text", "seller_name", "seller_type",
        "seller_active_since", "seller_ads_online", "seller_ads_total", "seller_badges",
        "views", "watchers", "reported_image_count", "dealer_name", "raw_signal_text",
    )
    for key in signal_fields:
        setattr(signals, key, result.signals.get(key))

    technical_values = extract_technical_data(_technical_scope(listing, snapshot))
    technical = db.scalar(select(ListingTechnicalData).where(ListingTechnicalData.listing_id == listing.id))
    if not technical:
        technical = ListingTechnicalData(listing_id=listing.id)
        db.add(technical)
    technical.data_json = dumps_technical_data(technical_values)

    # Only gross weight is promoted into the generic weight field.
    if technical_values.get("gross_weight_kg"):
        listing.weight_kg = technical_values["gross_weight_kg"]
    if technical_values.get("seats"):
        listing.seats = technical_values["seats"]
    if technical_values.get("moisture_issue"):
        listing.dry_status = "unknown"

    db.commit()
    db.refresh(listing)
    return _review_payload(listing)
