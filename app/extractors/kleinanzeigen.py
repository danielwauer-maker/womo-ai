import re

from .base import BaseExtractor, ExtractionResult
from ..technical_data import extract_technical_data


class KleinanzeigenExtractor(BaseExtractor):
    source = "Kleinanzeigen"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        description = kwargs.get("description") or ""
        text = kwargs.get("page_text") or ""
        combined = "\n".join([description, text])

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

        technical = extract_technical_data(combined)
        if technical.get("gross_weight_kg"):
            result.fields["weight_kg"] = technical["gross_weight_kg"]
            result.evidence["weight_kg"] = "kleinanzeigen_description"
        if technical.get("seats"):
            result.fields["seats"] = technical["seats"]
            result.evidence["seats"] = "kleinanzeigen_description"
        if technical.get("moisture_issue"):
            result.evidence["moisture_issue"] = "kleinanzeigen_description"
        if technical.get("engine_replaced"):
            result.evidence["engine_replaced"] = "kleinanzeigen_description"
        if technical.get("engine_overhauled"):
            result.evidence["engine_overhauled"] = "kleinanzeigen_description"
        if technical.get("historic_vehicle"):
            result.evidence["historic_vehicle"] = "kleinanzeigen_description"

        # Kleinanzeigen descriptions often carry maintenance details in prose.
        maintenance_patterns = {
            "timing_belt": r"Zahnriemen.{0,45}(?:gewechselt|erneuert|neu)",
            "gas_test": r"Gaspr[üu]fung.{0,45}(?:bis|neu|gültig)",
            "inspection": r"(?:T[ÜU]V|HU).{0,45}(?:bis|neu|gültig)",
            "solar": r"\bSolar(?:anlage|panel|modul)?\b",
            "heater": r"\bStandheizung\b",
            "battery": r"(?:Aufbau|Zweit|Wohnraum)?batterie.{0,35}(?:neu|erneuert|gewechselt)",
        }
        for key, pattern in maintenance_patterns.items():
            m = re.search(pattern, combined, re.I)
            if m:
                result.evidence[key] = m.group(0).strip()

        return result
