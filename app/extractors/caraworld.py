import re

from .base import BaseExtractor, ExtractionResult


class CaraworldExtractor(BaseExtractor):
    source = "Caraworld"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        text = kwargs.get("page_text") or ""

        m = re.search(r"Caraworld ID\s+([^\n]+)", text, re.I)
        if m:
            result.signals["portal_listing_id"] = m.group(1).strip()[:120]
        m = re.search(r"(?:Anbieter|Händlerlogo)\s*\n?\s*([^\n]{2,100})", text, re.I)
        if m:
            result.signals["dealer_name"] = m.group(1).strip()
        return result
