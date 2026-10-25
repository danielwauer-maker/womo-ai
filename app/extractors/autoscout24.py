import re

from .base import BaseExtractor, ExtractionResult
from ..technical_data import extract_technical_data


class AutoScout24Extractor(BaseExtractor):
    source = "AutoScout24"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        title = kwargs.get("title") or ""
        description = kwargs.get("description") or ""
        page_text = kwargs.get("page_text") or ""
        combined = "\n".join([title, description, page_text])

        m = re.search(r"-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", title, re.I)
        if not m:
            m = re.search(r"\b([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b", page_text, re.I)
        if m:
            result.signals["portal_listing_id"] = m.group(1)

        technical = extract_technical_data(combined)
        if technical.get("gross_weight_kg"):
            result.fields["weight_kg"] = technical["gross_weight_kg"]
            result.evidence["weight_kg"] = "autoscout24_technical"
        if technical.get("seats"):
            result.fields["seats"] = technical["seats"]
            result.evidence["seats"] = "autoscout24_technical"

        # Common AutoScout labels that are not always caught by generic text.
        power = self.int_match(r"(?:Leistung|Motorleistung)\s*[:\-]?\s*(\d{2,3})\s*kW", combined)
        if power:
            result.fields["power_kw"] = power
            result.evidence["power_kw"] = "autoscout24_technical"

        if re.search(r"\bAlkoven\b", combined, re.I):
            result.fields["body_type"] = "Alkoven"

        # Preserve explicit risk evidence for later technical-data review.
        if technical.get("moisture_issue"):
            result.evidence["moisture_issue"] = "autoscout24_description"
        if technical.get("condition_findings"):
            result.evidence["condition_findings"] = "autoscout24_description"

        # Dealer name fallback from visible seller block.
        dealer_patterns = [
            r"(?:Händler|Anbieter)\s*\n\s*([^\n]{2,120})",
            r"Verkäufer\s*\n\s*([^\n]{2,120})",
        ]
        for pattern in dealer_patterns:
            dm = re.search(pattern, page_text, re.I)
            if dm:
                result.signals["dealer_name"] = dm.group(1).strip()
                break

        return result
