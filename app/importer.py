import json
import re
from html import unescape
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ImportState, Listing
from .repository import upsert_listing

RESTRICTED_HOSTS = (
    "kleinanzeigen.de",
    "mobile.de",
    "autoscout24.de",
    "autoscout24.com",
)

META_RE = re.compile(r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\'][^>]*>', re.I)
META_RE_REV = re.compile(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']([^"\']+)["\'][^>]*>', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[\.\s]\d{3})+|\d{4,6})\s*€")
YEAR_RE = re.compile(r"\b(19[7-9]\d|20[0-2]\d)\b")
MILEAGE_RE = re.compile(r"(\d{1,3}(?:[\.\s]\d{3})+)\s*km", re.I)


def is_restricted(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in RESTRICTED_HOSTS)


def source_id_from_url(url: str) -> str | None:
    path = urlparse(url).path
    if "kleinanzeigen" in url:
        m = re.search(r"/(\d{8,})-", path)
        return m.group(1) if m else None
    if "mobile.de" in url:
        m = re.search(r"/(\d{6,})\.html", path)
        return m.group(1) if m else None
    if "autoscout24" in url.lower():
        parts = [p for p in path.split("/") if p]
        return parts[-1] if parts else None
    return None


def title_from_url(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts:
        return "Noch nicht analysiert"
    slug = parts[-1]
    slug = re.sub(r"\.(html?|php)$", "", slug, flags=re.I)
    slug = re.sub(r"[-_]", " ", slug)
    slug = re.sub(r"\b\d{6,}\b", "", slug)
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug[:300].title() if slug else "Noch nicht analysiert"


def _set_state(db: Session, listing: Listing, state: str, message: str = "") -> ImportState:
    row = db.scalar(select(ImportState).where(ImportState.listing_id == listing.id))
    if not row:
        row = ImportState(listing_id=listing.id)
        db.add(row)
    row.state = state
    row.message = message[:500]
    db.commit()
    db.refresh(row)
    return row


def process_listing(db: Session, listing: Listing) -> ImportState:
    _set_state(db, listing, "processing", "Import wird verarbeitet")
    inferred = {
        "source": listing.source,
        "url": listing.url,
        "source_id": listing.source_id or source_id_from_url(listing.url),
    }
    if not listing.title or listing.title == "Noch nicht analysiert":
        inferred["title"] = title_from_url(listing.url)
    upsert_listing(db, inferred)
    db.refresh(listing)

    if is_restricted(listing.url):
        return _set_state(
            db,
            listing,
            "awaiting_details",
            "URL archiviert. Für diese Quelle werden ohne freigegebene API keine automatisierten Seitendaten abgerufen.",
        )

    try:
        data = fetch_public_metadata(listing.url)
        data.update({"source": listing.source, "url": listing.url, "source_id": listing.source_id})
        upsert_listing(db, data)
        db.refresh(listing)
        if data.get("title") or data.get("description") or data.get("price"):
            return _set_state(db, listing, "extracted", "Öffentliche Metadaten wurden übernommen")
        return _set_state(db, listing, "awaiting_details", "Keine verwertbaren Metadaten gefunden")
    except Exception as exc:
        return _set_state(db, listing, "failed", f"Automatische Extraktion fehlgeschlagen: {type(exc).__name__}")


def fetch_public_metadata(url: str) -> dict:
    headers = {"User-Agent": "WomoAI/0.4 (+manual-user-import)"}
    with httpx.Client(timeout=12.0, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            return {}
        html = response.text[:2_000_000]

    meta: dict[str, str] = {}
    for key, value in META_RE.findall(html):
        meta[key.lower()] = unescape(value.strip())
    for value, key in META_RE_REV.findall(html):
        meta[key.lower()] = unescape(value.strip())

    result: dict = {}
    title = meta.get("og:title") or meta.get("twitter:title")
    if not title:
        m = TITLE_RE.search(html)
        title = unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else None
    description = meta.get("og:description") or meta.get("description") or meta.get("twitter:description")
    image = meta.get("og:image") or meta.get("twitter:image")
    if title:
        result["title"] = title[:300]
    if description:
        result["description"] = description[:12000]
    if image:
        result["image_urls"] = [image]

    for raw in JSONLD_RE.findall(html):
        try:
            payload = json.loads(raw.strip())
        except Exception:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            offers = item.get("offers") or {}
            if isinstance(offers, dict) and offers.get("price"):
                try:
                    result["price"] = int(float(str(offers["price"]).replace(",", ".")))
                except Exception:
                    pass
            if not result.get("title") and item.get("name"):
                result["title"] = str(item["name"])[:300]
            if not result.get("description") and item.get("description"):
                result["description"] = str(item["description"])[:12000]
            images = item.get("image")
            if images and not result.get("image_urls"):
                if isinstance(images, str):
                    result["image_urls"] = [images]
                elif isinstance(images, list):
                    result["image_urls"] = [str(x) for x in images[:10] if x]

    text = " ".join([result.get("title", ""), result.get("description", "")])
    if "price" not in result:
        m = PRICE_RE.search(text)
        if m:
            result["price"] = int(re.sub(r"[^0-9]", "", m.group(1)))
    m = YEAR_RE.search(text)
    if m:
        result["year"] = int(m.group(1))
    m = MILEAGE_RE.search(text)
    if m:
        result["mileage"] = int(re.sub(r"[^0-9]", "", m.group(1)))
    return result
