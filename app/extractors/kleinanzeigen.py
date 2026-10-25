import re

from .base import BaseExtractor, ExtractionResult


class KleinanzeigenExtractor(BaseExtractor):
    source = "Kleinanzeigen"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        text = kwargs.get("page_text") or ""

        m = re.search(r"Anzeigen-ID\s*([0-9]{6,})", text, re.I)
        if m:
            result.signals["portal_listing_id"] = m.group(1)
        m = re.search(r"Aktiv seit\s+([^\n]+)", text, re.I)
        if m:
            result.signals["seller_active_since"] = m.group(1).strip()[:80]
        m = re.search(r"\b(Privater Nutzer|Gewerblicher Nutzer)\b", text, re.I)
        if m:
            result.signals["seller_type"] = m.group(1)
        online = self.int_match(r"([\d.]+)\s+Anzeigen online", text)
        total = self.int_match(r"([\d.]+)\s+Anzeigen gesamt", text)
        if online is not None:
            result.signals["seller_ads_online"] = online
        if total is not None:
            result.signals["seller_ads_total"] = total

        badges = [
            badge for badge in (
                "TOP Zufriedenheit", "Besonders freundlich", "Sehr freundlich",
                "Besonders zuverlässig", "Sehr zuverlässig"
            ) if badge.lower() in text.lower()
        ]
        if badges:
            result.signals["seller_badges"] = ", ".join(badges)
        return result
