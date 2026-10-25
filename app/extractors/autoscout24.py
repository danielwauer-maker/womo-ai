import re

from .base import BaseExtractor, ExtractionResult


class AutoScout24Extractor(BaseExtractor):
    source = "AutoScout24"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        title = kwargs.get("title") or ""
        page_text = kwargs.get("page_text") or ""

        m = re.search(r"-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", title, re.I)
        if not m:
            m = re.search(r"\b([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b", page_text, re.I)
        if m:
            result.signals["portal_listing_id"] = m.group(1)
        return result
