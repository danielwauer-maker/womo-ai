from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Listing, ListingImage, PriceHistory


def upsert_listing(db: Session, data: dict) -> Listing:
    listing = None
    if data.get("source_id"):
        listing = db.scalar(select(Listing).where(Listing.source == data["source"], Listing.source_id == data["source_id"]))
    if not listing and data.get("url"):
        listing = db.scalar(select(Listing).where(Listing.url == data["url"]))

    if not listing:
        listing = Listing(source=data.get("source", "manual"), url=data.get("url", ""), source_id=data.get("source_id"))
        db.add(listing)
        db.flush()

    previous_price = listing.price
    for field in [
        "source_id", "url", "title", "description", "price", "year", "mileage", "distance_km",
        "location", "make", "model", "body_type", "engine", "power_kw", "seats", "weight_kg",
        "three_point_belt", "dry_status", "repair_level", "score", "score_explanation", "status"
    ]:
        if field in data and data[field] is not None:
            setattr(listing, field, data[field])

    listing.last_seen_at = data.get("last_seen_at") or datetime.utcnow()
    listing.status = data.get("status", "active")
    listing.inactive_at = None

    if listing.price is not None and (previous_price != listing.price or not listing.prices):
        db.add(PriceHistory(listing_id=listing.id, price=int(listing.price)))

    existing_urls = {img.remote_url for img in listing.images}
    for index, url in enumerate(data.get("image_urls", [])):
        if url and url not in existing_urls:
            db.add(ListingImage(listing_id=listing.id, remote_url=url, sort_order=index))

    db.commit()
    db.refresh(listing)
    return listing


def mark_not_seen_inactive(db: Session, source: str, seen_source_ids: set[str]) -> int:
    rows = db.scalars(select(Listing).where(Listing.source == source, Listing.status == "active")).all()
    count = 0
    now = datetime.utcnow()
    for listing in rows:
        if listing.source_id and listing.source_id not in seen_source_ids:
            listing.status = "inactive"
            listing.inactive_at = now
            count += 1
    db.commit()
    return count
