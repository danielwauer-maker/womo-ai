import re

from .base import BaseExtractor, ExtractionResult
from ..technical_data import extract_technical_data


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

        images = self.int_match(r"([0-9]{1,3})\s+Bilder", text)
        if images:
            result.signals["reported_image_count"] = images

        technical = extract_technical_data(combined)
        if technical.get("gross_weight_kg"):
            result.fields["weight_kg"] = technical["gross_weight_kg"]
            result.evidence["weight_kg"] = "caraworld_technical"
        if technical.get("seats"):
            result.fields["seats"] = technical["seats"]
            result.evidence["seats"] = "caraworld_technical"
        if technical.get("sleeping_places"):
            result.evidence["sleeping_places"] = "caraworld_technical"

        power = self.int_match(r"Leistung\s*[:\-]?\s*(\d{2,3})\s*kW", combined)
        if power:
            result.fields["power_kw"] = power
            result.evidence["power_kw"] = "caraworld_technical"

        # Caraworld presents base vehicle very consistently.
        base_match = re.search(r"(?:Basisfahrzeug|Basis Fahrzeug|Fahrgestell)\s*[:\-]?\s*([^\n\r]+)", combined, re.I)
        if base_match:
            base = base_match.group(1).strip()
            parts = base.split(maxsplit=1)
            if parts:
                result.identity["base_make"] = parts[0]
            if len(parts) > 1:
                result.identity["base_model"] = parts[1]
            result.evidence["base_vehicle"] = "caraworld_technical"

        if re.search(r"\bAlkoven\b", combined, re.I):
            result.fields["body_type"] = "Alkoven"

        if technical.get("engine_overhauled"):
            result.evidence["engine_overhauled"] = "caraworld_description"
        if technical.get("historic_vehicle"):
            result.evidence["historic_vehicle"] = "caraworld_description"

        return result
