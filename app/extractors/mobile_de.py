import re
from urllib.parse import urlparse

from .base import BaseExtractor, ExtractionResult, dedupe_urls


class MobileDeExtractor(BaseExtractor):
    source = "mobile.de"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        description = kwargs.get("description") or ""
        title = kwargs.get("title") or ""
        page_text = kwargs.get("page_text") or ""
        primary = f"{title}\n{description}"

        # Objective values from the provider description.
        weight = self.int_match(r"Zul[aä]ssiges\s+Gesamtgewicht\s*[:\-]?\s*([\d\.\s]+)\s*kg", primary)
        if weight:
            result.fields["weight_kg"] = weight
            result.evidence["weight_kg"] = "provider_description"

        power = self.int_match(r"Leistung\s*[:\-]?\s*(\d{2,3})\s*kW", primary)
        if power:
            result.fields["power_kw"] = power
            result.evidence["power_kw"] = "provider_description"

        seats = self.int_match(r"Sitzpl[aä]tze\s*[:\-]?\s*(\d)", primary)
        if seats:
            result.fields["seats"] = seats
            result.evidence["seats"] = "provider_description"

        displacement = self.int_match(r"Hubraum\s*[:\-]?\s*([\d\.\s]+)\s*cm", primary)
        fuel = None
        m = re.search(r"Kraftstoff\s*[:\-]?\s*([^\n\r]+)", primary, re.I)
        if m:
            fuel = m.group(1).strip()
        if displacement and fuel and "diesel" in fuel.lower():
            litres = displacement / 1000
            result.fields["engine"] = f"{litres:.1f} l Diesel ({displacement} cm³)"
            result.identity["engine"] = result.fields["engine"]
            result.evidence["engine"] = "provider_description"
        elif "engine" in result.fields:
            # Never keep an engine inferred from page-wide recommendation text.
            result.fields.pop("engine", None)
            result.identity.pop("engine", None)

        # Ford Transit etc.
        m = re.search(r"Fahrzeugtyp/Basis\s*[:\-]?\s*([^\n\r]+)", primary, re.I)
        if m:
            base = m.group(1).strip()
            parts = base.split(maxsplit=1)
            result.identity["base_make"] = parts[0]
            if len(parts) > 1:
                result.identity["base_model"] = parts[1]
            result.evidence["base_vehicle"] = "provider_description"

        # mobile.de often writes the coachbuilder in the description, e.g. Roller Team 275.
        m = re.search(r"Wohnmobil\s+(?:Ford\s+)?([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\- ]+?)\s+([A-Za-z0-9][A-Za-z0-9\- ]{0,20})\s+mit\s+folgenden", primary, re.I)
        if m:
            result.identity["coachbuilder"] = m.group(1).strip()
            result.identity["coach_model"] = m.group(2).strip()
            result.evidence["coachbuilder"] = "provider_description"
        else:
            m = re.search(r"Wohnmobil-Ausbau\s*[:\-]?\s*([^\n\r]+)", primary, re.I)
            if m:
                result.identity["coachbuilder"] = m.group(1).strip()

        # Compact useful signals from provider description.
        if re.search(r"T[ÜU]V/AU\s+neu", primary, re.I):
            result.signals["tuev_text"] = "TÜV/AU neu"
        if re.search(r"Serviceheft\s+gepflegt", primary, re.I):
            result.signals["service_history"] = "Serviceheft gepflegt"
        if re.search(r"Austauschmotor", primary, re.I):
            result.signals["engine_replaced"] = True

        # Strict image filtering for mobile.de vehicle CDN and query-size dedupe.
        candidates = result.images
        vehicle = []
        for url in candidates:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            path = parsed.path.lower()
            if "classistatic" in host and ("mo-prod/images" in path or "/images/" in path):
                vehicle.append(url)
        if vehicle:
            candidates = vehicle
        best = {}
        for url in candidates:
            parsed = urlparse(url)
            key = f"{parsed.netloc.lower()}{parsed.path}"
            score = 0
            for marker, points in (("mo-2000", 2000), ("mo-1600", 1600), ("mo-1280", 1280), ("mo-1024", 1024), ("mo-800", 800)):
                if marker in url.lower():
                    score = points
                    break
            current = best.get(key)
            if current is None or score > current[0]:
                best[key] = (score, url)
        result.images = dedupe_urls([x[1] for x in best.values()])

        # Listing ID from text fallback if present.
        m = re.search(r"\bid\s*[=:]\s*([0-9]{8,})\b", page_text, re.I)
        if m:
            result.signals["portal_listing_id"] = m.group(1)

        return result
