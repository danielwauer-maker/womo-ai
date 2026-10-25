import re

from .base import BaseExtractor, ExtractionResult
from ..technical_data import extract_technical_data


def _normalize_caraworld_images(urls: list[str]) -> list[str]:
    seen, result = set(), []
    for url in urls:
        if "/bilder/i/" not in url:
            continue
        m = re.search(r"https://(?:www\.)?cdn?\.caraworld\.(?:de|com)/bilder/i/[^?]+", url, re.I)
        if not m:
            m = re.search(r"https://www\.caraworld\.de/bilder/i/[^?]+", url, re.I)
        if not m:
            continue
        clean = m.group(0)
        identity = re.sub(r"-3-(?:220|728)-0(?=\.)", "", clean)
        identity = identity.replace("https://www.caraworld.de", "https://cdn.caraworld.com")
        if identity in seen:
            continue
        seen.add(identity)
        preferred = re.sub(r"-3-220-0(?=\.)", "-3-728-0", clean)
        preferred = preferred.replace("https://www.caraworld.de", "https://cdn.caraworld.com")
        result.append(preferred)
    return result


class CaraworldExtractor(BaseExtractor):
    source = "Caraworld"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        description = kwargs.get("description") or ""
        text = kwargs.get("page_text") or ""
        combined = "\n".join([description, text])

        m = re.search(r"Caraworld ID\s+([^\n]+)", text, re.I)
        if m:
            result.signals["portal_listing_id"] = m.group(1).strip()[:120]
        m = re.search(r"(?:Anbieter|Händlerlogo|Händlerseite)\s*\n?\s*([^\n]{2,100})", text, re.I)
        if m:
            result.signals["dealer_name"] = m.group(1).strip()

        reported = self.int_match(r"([0-9]{1,3})\s+Bilder", text)
        if reported:
            result.signals["reported_image_count"] = reported

        technical = extract_technical_data(combined)
        if technical.get("gross_weight_kg"):
            result.fields["weight_kg"] = technical["gross_weight_kg"]
            result.evidence["weight_kg"] = "caraworld_technical"
        if technical.get("seats"):
            result.fields["seats"] = technical["seats"]
            result.evidence["seats"] = "caraworld_technical"
        if technical.get("sleeping_places"):
            result.evidence["sleeping_places"] = "caraworld_technical"

        power = self.int_match(r"(?:^|\n)Leistung\s*\n?\s*(\d{2,3})\s*kW", text)
        if power:
            result.fields["power_kw"] = power
            result.evidence["power_kw"] = "caraworld_technical"

        base_match = re.search(r"(?:^|\n)Basisfahrzeug\s*\n?\s*([^\n\r]+)", text, re.I)
        if base_match:
            base = base_match.group(1).strip()
            parts = base.split(maxsplit=1)
            if parts:
                result.identity["base_make"] = parts[0]
            if len(parts) > 1:
                result.identity["base_model"] = parts[1]
            result.evidence["base_vehicle"] = "caraworld_technical"

        if re.search(r"(?:^|\n)Aufbauart\s*\n?\s*Alkoven(?:\n|$)", text, re.I) or re.search(r"\bAlkoven\b", description, re.I):
            result.fields["body_type"] = "Alkoven"

        # Never accept a coachbuilder that only appears in recommendations/footer.
        header = "\n".join([line for line in text.splitlines() if line.strip()][:45])
        coach = result.identity.get("coachbuilder")
        if coach and not re.search(rf"\b{re.escape(coach)}\b", header, re.I) and not re.search(rf"\b{re.escape(coach)}\b", description, re.I):
            result.identity.pop("coachbuilder", None)
            result.identity.pop("coach_model", None)

        if technical.get("engine_overhauled"):
            result.evidence["engine_overhauled"] = "caraworld_description"
        if "historic_vehicle" in technical:
            result.evidence["historic_vehicle"] = "caraworld_description"

        normalized = _normalize_caraworld_images(result.images)
        if normalized:
            result.images = normalized

        return result
