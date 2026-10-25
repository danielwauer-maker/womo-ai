import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..text_enrichment import extract_listing_text, extract_vehicle_identity


@dataclass
class ExtractionResult:
    fields: dict[str, Any] = field(default_factory=dict)
    identity: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def dedupe_urls(urls: list[str]) -> list[str]:
    seen, result = set(), []
    for url in urls:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


class BaseExtractor:
    source = "generic"

    def extract(self, *, title: str, description: str, page_text: str, structured_data: str, image_urls_json: str) -> ExtractionResult:
        primary = "\n\n".join(x for x in [description] if x).strip()
        fields = extract_listing_text(primary, current_title=title)
        fallback = extract_listing_text(page_text[:35000], current_title=title)
        for key in ("price", "year", "mileage", "power_kw", "weight_kg", "seats", "body_type", "three_point_belt", "dry_status", "repair_level"):
            if key not in fields and key in fallback:
                fields[key] = fallback[key]

        identity = extract_vehicle_identity(primary_text=primary, current_title=title, fallback_text=page_text[:35000])
        if identity.get("engine"):
            fields["engine"] = identity["engine"]

        return ExtractionResult(
            fields=fields,
            identity=identity,
            images=dedupe_urls(_json_list(image_urls_json)),
        )

    @staticmethod
    def int_match(pattern: str, text: str) -> int | None:
        m = re.search(pattern, text or "", re.I)
        if not m:
            return None
        digits = re.sub(r"\D", "", m.group(1))
        return int(digits) if digits else None
