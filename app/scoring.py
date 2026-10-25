from dataclasses import dataclass

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

def score_listing(listing: dict, criteria: SearchCriteria) -> tuple[int, list[str]]:
    score = 70
    reasons: list[str] = []
    price = listing.get("price")
    distance = listing.get("distance_km")
    year = listing.get("year")
    mileage = listing.get("mileage")
    weight = listing.get("weight_kg")
    body = (listing.get("body_type") or "").lower()
    engine = (listing.get("engine") or "").lower()
    belt = listing.get("three_point_belt")
    dry = listing.get("dry_status") or "unknown"
    repair = listing.get("repair_level") or "unknown"

    if price is None:
        score -= 8; reasons.append("Preis unbekannt")
    elif price > criteria.max_price:
        score -= min(35, int((price - criteria.max_price) / 200)); reasons.append("über Budget")
    elif price <= criteria.max_price * 0.75:
        score += 8
    else:
        score += 4

    if distance is None:
        score -= 3
    elif distance > criteria.max_distance_km:
        score -= 15; reasons.append("außerhalb Suchradius")

    if year is None:
        score -= 3
    elif year < criteria.min_year:
        score -= 8; reasons.append("älter als Wunschbereich")

    if mileage is None:
        score -= 3
    elif mileage > criteria.max_mileage:
        score -= 12; reasons.append("hohe Laufleistung")

    if criteria.require_three_point_belt:
        if belt is True:
            score += 5
        elif belt is False:
            score -= 24; reasons.append("3-Punkt-Gurt fehlt")
        else:
            score -= 14; reasons.append("3-Punkt-Gurt ungeklärt")

    if weight is None:
        score -= 3
    elif weight > criteria.max_weight_kg:
        score -= 20; reasons.append("zu hohes Gesamtgewicht")

    if criteria.require_alkoven:
        if body == "alkoven" or "alcove" in body:
            score += 4
        elif body:
            score -= 25; reasons.append("kein Alkoven")
        else:
            score -= 6; reasons.append("Aufbauart ungeklärt")

    preferred = criteria.preferred_engine.lower().strip()
    if preferred:
        if preferred in engine:
            score += 8
        elif engine:
            score -= 8; reasons.append("Motor nicht bevorzugt")
        else:
            score -= 3

    if dry == "measured_dry":
        score += 8
    elif dry == "claimed_dry":
        score += 2
    else:
        score -= 6; reasons.append("Feuchtigkeit ungeklärt")

    if REPAIR_RANK.get(repair, 2) > REPAIR_RANK.get(criteria.repair_tolerance, 2):
        score -= 14; reasons.append("zu hoher Reparaturbedarf")
    elif repair == "light":
        score += 3

    return max(0, min(100, score)), reasons

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
