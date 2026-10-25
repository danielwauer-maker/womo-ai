from typing import Any


CORE_FIELDS = [
    ("price", 7),
    ("year", 5),
    ("mileage", 6),
    ("base_make", 7),
    ("base_model", 6),
    ("coachbuilder", 7),
    ("coach_model", 5),
    ("body_type", 5),
    ("engine", 6),
    ("power_kw", 4),
    ("weight_kg", 7),
    ("seats", 5),
    ("description", 4),
    ("images", 5),
    ("portal_listing_id", 3),
]

# Technical completeness deliberately emphasizes safety/state over comfort equipment.
TECHNICAL_FIELDS = [
    ("first_registration", 3),
    ("fuel", 3),
    ("displacement_cc", 3),
    ("transmission", 3),
    ("gross_weight_kg", 5),
    ("seats", 4),
    ("inspection", 4),
    ("gas_inspection", 3),
    ("service_history", 2),
    ("condition_findings", 7),
    ("moisture_issue", 8),
    ("engine_replaced", 3),
    ("engine_overhauled", 3),
]


def _present(value: Any, field: str) -> bool:
    if field == "images":
        return isinstance(value, list) and len(value) > 0
    # False is a meaningful known value for booleans such as moisture_issue.
    return value is not None and value not in ("", [], {})


def quality_report(data: dict[str, Any]) -> dict[str, Any]:
    technical = data.get("technical") if isinstance(data.get("technical"), dict) else {}
    total = sum(weight for _, weight in CORE_FIELDS) + sum(weight for _, weight in TECHNICAL_FIELDS)
    earned = 0
    present, missing = [], []

    for field, weight in CORE_FIELDS:
        value = data.get(field)
        if _present(value, field):
            earned += weight
            present.append(field)
        else:
            missing.append(field)

    for field, weight in TECHNICAL_FIELDS:
        value = technical.get(field)
        name = f"technical.{field}"
        if _present(value, field):
            earned += weight
            present.append(name)
        else:
            missing.append(name)

    return {
        "score": round(earned / total * 100) if total else 0,
        "present": present,
        "missing": missing,
        "weighted_total": total,
        "weighted_earned": earned,
        "critical_known": [name for name in present if name in {
            "weight_kg", "seats", "technical.inspection", "technical.gas_inspection",
            "technical.condition_findings", "technical.moisture_issue"
        }],
    }
