import re

from .base import BaseExtractor, ExtractionResult
from ..technical_data import extract_technical_data


def _normalize_autoscout_images(urls: list[str]) -> list[str]:
    seen, result = set(), []
    for url in urls:
        if "prod.pictures.autoscout24.net/listing-images/" not in url:
            continue
        m = re.search(r"(https://prod\.pictures\.autoscout24\.net/listing-images/[^/?]+)", url, re.I)
        if not m:
            continue
        base = m.group(1)
        identity = base.rsplit("_", 1)[-1].lower()
        if identity in seen:
            continue
        seen.add(identity)
        result.append(base + "/1920x1080.webp")
    return result


class AutoScout24Extractor(BaseExtractor):
    source = "AutoScout24"

    def extract(self, **kwargs) -> ExtractionResult:
        result = super().extract(**kwargs)
        title = kwargs.get("title") or ""
        description = kwargs.get("description") or ""
        page_text = kwargs.get("page_text") or ""
        combined = "\n".join([description, page_text])

        m = re.search(r"\b([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b", kwargs.get("image_urls_json") or "", re.I)
        if not m:
            m = re.search(r"\b([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b", page_text, re.I)
        if m:
            result.signals["portal_listing_id"] = m.group(1)

        technical = extract_technical_data(combined)
        # Do not map empty/curb weight to gross weight.
        if technical.get("gross_weight_kg"):
            result.fields["weight_kg"] = technical["gross_weight_kg"]
            result.evidence["weight_kg"] = "autoscout24_gross_weight"
        elif result.fields.get("weight_kg") == technical.get("empty_weight_kg"):
            result.fields.pop("weight_kg", None)

        if technical.get("seats"):
            result.fields["seats"] = technical["seats"]
            result.evidence["seats"] = "autoscout24_technical"

        power = self.int_match(r"(?:^|\n)Leistung\s*\n?\s*(\d{2,3})\s*kW", page_text)
        if power:
            result.fields["power_kw"] = power
            result.evidence["power_kw"] = "autoscout24_technical"

        if re.search(r"(?:^|\n)Alkoven(?:\n|$)", page_text, re.I) or re.search(r"\bAlkoven\b", description, re.I):
            result.fields["body_type"] = "Alkoven"

        # The listing heading is a safer model source than recommendations/footer text.
        heading_lines = [x.strip() for x in page_text.splitlines() if x.strip()][:40]
        if result.identity.get("coachbuilder"):
            maker = result.identity["coachbuilder"]
            for i, line in enumerate(heading_lines):
                if line.lower() == maker.lower() and i + 1 < len(heading_lines):
                    candidate = heading_lines[i + 1]
                    if 2 <= len(candidate) <= 80 and not candidate.startswith("€"):
                        result.identity["coach_model"] = candidate
                    break

        if technical.get("moisture_issue"):
            result.evidence["moisture_issue"] = "autoscout24_description"
        if technical.get("condition_findings"):
            result.evidence["condition_findings"] = "autoscout24_description"

        dealer_patterns = [
            r"(?:^|\n)(Auto [^\n]{2,100}|[^\n]{2,100} GmbH|[^\n]{2,100} KG)(?:\n)",
            r"(?:Händler|Anbieter)\s*\n\s*([^\n]{2,120})",
        ]
        for pattern in dealer_patterns:
            dm = re.search(pattern, page_text, re.I)
            if dm:
                result.signals["dealer_name"] = dm.group(1).strip()
                break

        normalized = _normalize_autoscout_images(result.images)
        if normalized:
            result.images = normalized
            result.signals["reported_image_count"] = self.int_match(r"\b1\s*/\s*(\d{1,3})\b", page_text)

        return result
