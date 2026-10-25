import os
from datetime import datetime
import httpx

BASE_URL = "https://services.mobile.de"

class MobileDeCollector:
    name = "mobile.de"

    @property
    def configured(self) -> bool:
        return bool(os.getenv("MOBILE_API_USERNAME") and os.getenv("MOBILE_API_PASSWORD"))

    def search(self, criteria, page: int = 1, page_size: int = 50) -> list[dict]:
        if not self.configured:
            return []
        params = {
            "classification": "refdata/classes/Motorhome",
            "country": "DE",
            "condition": "USED",
            "price.max": criteria.max_price,
            "mileage.max": criteria.max_mileage,
            "firstRegistration.min": f"{criteria.min_year}-01",
            "numSeats.min": 3,
            "page.number": page,
            "page.size": min(page_size, 100),
            "sort.field": "creationTime",
            "sort.order": "DESCENDING",
        }
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{BASE_URL}/search-api/search",
                params=params,
                auth=(os.environ["MOBILE_API_USERNAME"], os.environ["MOBILE_API_PASSWORD"]),
                headers={"Accept": "application/vnd.de.mobile.api+json"},
            )
            response.raise_for_status()
            data = response.json()
        return [self._normalize(ad) for ad in data.get("ads", [])]

    def fetch_detail(self, source_id: str) -> dict:
        if not self.configured:
            raise RuntimeError("mobile.de API credentials not configured")
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{BASE_URL}/search-api/ad/{source_id}",
                auth=(os.environ["MOBILE_API_USERNAME"], os.environ["MOBILE_API_PASSWORD"]),
                headers={"Accept": "application/vnd.de.mobile.api+json"},
            )
            response.raise_for_status()
            return self._normalize(response.json())

    def _normalize(self, ad: dict) -> dict:
        price = ad.get("price", {})
        seller = ad.get("seller", {})
        images = ad.get("images") or []
        registration = ad.get("firstRegistration") or ""
        return {
            "source": self.name,
            "source_id": str(ad.get("mobileAdId") or ad.get("id") or ""),
            "url": ad.get("detailPageUrl") or "",
            "title": ad.get("modelDescription") or "Wohnmobil",
            "description": ad.get("plainTextDescription") or ad.get("description") or "",
            "price": price.get("consumerPriceGross") or price.get("gross") or ad.get("priceAmount"),
            "year": int(registration[:4]) if len(registration) >= 4 and registration[:4].isdigit() else None,
            "mileage": ad.get("mileage"),
            "location": seller.get("address", {}).get("city") if isinstance(seller.get("address"), dict) else None,
            "make": ad.get("make"),
            "model": ad.get("modelDescription"),
            "body_type": "Alkoven" if ad.get("category") in {"Alcoves", "ALCOVES"} else ad.get("category"),
            "engine": " ".join(filter(None, [ad.get("make"), ad.get("modelDescription")])),
            "power_kw": ad.get("power"),
            "seats": ad.get("numSeats"),
            "weight_kg": ad.get("grossVehicleWeight"),
            "status": "active",
            "last_seen_at": datetime.utcnow(),
            "image_urls": [img.get("uri") or img.get("url") for img in images if isinstance(img, dict) and (img.get("uri") or img.get("url"))],
        }
