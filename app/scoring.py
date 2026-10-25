from dataclasses import dataclass
from typing import Any


@dataclass
class SearchCriteria:
    max_price: int = 11000
    max_distance_km: int = 300
    min_year: int = 1988
    max_mileage: int = 260000
    require_three_point_belt: bool = True
    max_weight_kg: int = 3500
    repair_tolerance: str = "medium"
    preferred_engine: str = "2.5 TD"
    require_alkoven: bool = True


REPAIR_RANK = {"unknown": 2, "light": 1, "medium": 2, "heavy": 3}


def _technical(listing: dict) -> dict:
    value = listing.get("technical")
    return value if isinstance(value, dict) else {}


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def assess_listing(listing: dict, criteria: SearchCriteria | None = None) -> dict[str, Any]:
    criteria = criteria or SearchCriteria()
    technical = _technical(listing)

    score = 50
    positives: list[str] = []
    risks: list[str] = []
    unknowns: list[str] = []
    blockers: list[str] = []

    price = listing.get("price")
    distance = listing.get("distance_km")
    year = listing.get("year")
    mileage = listing.get("mileage")
    weight = listing.get("weight_kg") or technical.get("gross_weight_kg")
    body = (listing.get("body_type") or "").lower()
    engine = (listing.get("engine_text") or listing.get("engine") or "").lower()
    base_make = (listing.get("base_make") or "").lower()
    base_model = (listing.get("base_model") or "").lower()
    belt = listing.get("three_point_belt")
    dry = listing.get("dry_status") or "unknown"
    repair = listing.get("repair_level") or "unknown"
    moisture_issue = technical.get("moisture_issue") is True

    # Price / value fit.
    if price is None:
        _append_unique(unknowns, "Preis unbekannt")
    elif price <= criteria.max_price * 0.70:
        score += 14
        _append_unique(positives, "deutlich unter Budget")
    elif price <= criteria.max_price:
        score += 10
        _append_unique(positives, "im Budget")
    elif price <= criteria.max_price * 1.15:
        score -= 8
        _append_unique(risks, "leicht über Budget")
    else:
        score -= min(30, 12 + int((price - criteria.max_price * 1.15) / 750))
        _append_unique(risks, "deutlich über Budget")

    # Body type is a strong preference, but unknown is not a failure.
    if criteria.require_alkoven:
        if body == "alkoven" or "alcove" in body:
            score += 10
            _append_unique(positives, "Alkoven passt zum Suchprofil")
        elif body:
            score -= 28
            _append_unique(blockers, "kein Alkoven")
        else:
            _append_unique(unknowns, "Aufbauart ungeklärt")

    # Child safety: only explicit 3-point-belt evidence counts.
    if criteria.require_three_point_belt:
        if belt is True:
            score += 14
            _append_unique(positives, "3-Punkt-Gurt hinten bestätigt")
        elif belt is False:
            score -= 35
            _append_unique(blockers, "3-Punkt-Gurt hinten fehlt")
        else:
            _append_unique(unknowns, "3-Punkt-Gurt hinten noch prüfen")

    # Moisture / water damage is the strongest condition signal.
    if moisture_issue:
        score -= 32
        _append_unique(blockers, "Feuchtigkeits-/Wasserschadenhinweis im Inserat")
    elif dry == "measured_dry":
        score += 14
        _append_unique(positives, "Feuchtigkeit gemessen unauffällig")
    elif dry == "claimed_dry":
        score += 4
        _append_unique(positives, "laut Anbieter trocken")
    else:
        _append_unique(unknowns, "Feuchtigkeit noch messen")

    # Repair tolerance.
    if repair == "heavy":
        score -= 25
        _append_unique(blockers, "hoher Reparaturbedarf")
    elif repair == "medium":
        score -= 6
        _append_unique(risks, "Reparatur-/Bastlerarbeiten einplanen")
    elif repair == "light":
        score += 4
        _append_unique(positives, "nur geringer Reparaturbedarf bekannt")
    else:
        _append_unique(unknowns, "Reparaturbedarf nicht abschließend geklärt")

    # Weight and licence suitability.
    if weight is None:
        _append_unique(unknowns, "zulässiges Gesamtgewicht ungeklärt")
    elif weight <= criteria.max_weight_kg:
        score += 8
        _append_unique(positives, "zGG bis 3,5 t")
    else:
        score -= 28
        _append_unique(blockers, "zGG über 3,5 t")

    # Age / mileage are relevant but should not dominate an old-motorhome search.
    if year is None:
        _append_unique(unknowns, "Baujahr/EZ ungeklärt")
    elif year >= criteria.min_year:
        score += 3
    else:
        score -= 5
        _append_unique(risks, "älter als Wunschbereich")

    if mileage is None:
        _append_unique(unknowns, "Kilometerstand ungeklärt")
    elif mileage <= 180000:
        score += 5
        _append_unique(positives, "moderate Laufleistung")
    elif mileage <= criteria.max_mileage:
        score += 1
    else:
        score -= 8
        _append_unique(risks, "hohe Laufleistung")

    # Base vehicle and engine preference.
    preferred_base = (
        (base_make == "fiat" and "ducato" in base_model)
        or (base_make == "peugeot" and ("j5" in base_model or "boxer" in base_model))
        or (base_make in {"citroën", "citroen"} and ("c25" in base_model or "jumper" in base_model))
    )
    if preferred_base:
        score += 7
        _append_unique(positives, "bevorzugtes Basisfahrzeug")
    elif base_make or base_model:
        score -= 2
        _append_unique(risks, "Basisfahrzeug nicht bevorzugt")
    else:
        _append_unique(unknowns, "Basisfahrzeug ungeklärt")

    preferred = criteria.preferred_engine.lower().replace(" ", "")
    engine_compact = engine.replace(" ", "")
    if engine:
        if preferred and (preferred in engine_compact or "2.5td" in engine_compact or "2.5lturbodiesel" in engine_compact):
            score += 8
            _append_unique(positives, "bevorzugter 2,5-TD-Motor")
        elif "diesel" in engine_compact or "td" in engine_compact or "tdi" in engine_compact:
            score += 1
    else:
        _append_unique(unknowns, "Motorisierung ungeklärt")

    # Inspection / history: useful positive signals, never substitutes for inspection.
    if technical.get("inspection") or technical.get("tuev"):
        score += 3
        _append_unique(positives, "HU/TÜV dokumentiert")
    if technical.get("gas_inspection"):
        score += 2
        _append_unique(positives, "Gasprüfung dokumentiert")
    if technical.get("engine_overhauled"):
        score += 3
        _append_unique(positives, "Motorüberholung angegeben")
    if technical.get("engine_replaced"):
        _append_unique(positives, "Austauschmotor angegeben")
        _append_unique(unknowns, "Nachweis/Laufleistung des Austauschmotors prüfen")

    # Distance is intentionally low weight.
    if distance is not None and distance > criteria.max_distance_km:
        score -= 5
        _append_unique(risks, "weite Anfahrt")

    score = max(0, min(100, round(score)))

    critical_checks = {
        "price": price is not None,
        "body": bool(body),
        "belt": belt is not None,
        "moisture": moisture_issue or dry in {"claimed_dry", "measured_dry"},
        "weight": weight is not None,
        "repair": repair != "unknown",
        "identity": bool(base_make or base_model),
        "mileage": mileage is not None,
    }
    known = sum(1 for value in critical_checks.values() if value)
    confidence = round(known / len(critical_checks) * 100)

    if blockers:
        verdict = "kritisch prüfen"
    elif score >= 85:
        verdict = "sehr interessant"
    elif score >= 72:
        verdict = "interessant"
    elif score >= 58:
        verdict = "mit Vorbehalt"
    else:
        verdict = "eher nicht passend"

    if confidence < 50 and not blockers:
        verdict = "zu wenig Daten"

    return {
        "score": score,
        "verdict": verdict,
        "confidence": confidence,
        "positives": positives,
        "risks": risks,
        "unknowns": unknowns,
        "blockers": blockers,
        "critical_checks": critical_checks,
    }


def score_listing(listing: dict, criteria: SearchCriteria) -> tuple[int, list[str]]:
    assessment = assess_listing(listing, criteria)
    reasons = list(assessment["blockers"])
    reasons.extend(assessment["risks"])
    reasons.extend(assessment["unknowns"])
    return assessment["score"], reasons


def matches_hard_filters(listing: dict, criteria: SearchCriteria) -> bool:
    price = listing.get("price")
    distance = listing.get("distance_km")
    weight = listing.get("weight_kg")
    body = (listing.get("body_type") or "").lower()
    if price is not None and price > criteria.max_price * 1.15:
        return False
    if distance is not None and distance > criteria.max_distance_km * 1.25:
        return False
    if weight is not None and weight > criteria.max_weight_kg + 250:
        return False
    if criteria.require_alkoven and body and body != "alkoven" and "alcove" not in body:
        return False
    return True
