from typing import Any


CORE_FIELDS = [
    ("price", 8),
    ("year", 6),
    ("mileage", 7),
    ("base_make", 8),
    ("base_model", 7),
    ("coachbuilder", 8),
    ("coach_model", 6),
    ("body_type", 6),
    ("engine", 7),
    ("power_kw", 5),
    ("weight_kg", 6),
    ("seats", 4),
    ("description", 5),
    ("images", 7),
    ("portal_listing_id", 4),
]


def quality_report(data: dict[str, Any]) -> dict[str, Any]:
    total = sum(weight for _, weight in CORE_FIELDS)
    earned = 0
    present, missing = [], []

    for field, weight in CORE_FIELDS:
        value = data.get(field)
        ok = False
        if field == "images":
            ok = isinstance(value, list) and len(value) > 0
        else:
            ok = value not in (None, "", [], {})
        if ok:
            earned += weight
            present.append(field)
        else:
            missing.append(field)

    return {
        "score": round(earned / total * 100) if total else 0,
        "present": present,
        "missing": missing,
        "weighted_total": total,
        "weighted_earned": earned,
    }
