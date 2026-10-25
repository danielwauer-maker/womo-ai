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
    preferred_engine: str = "2.5"
    require_alkoven: bool = True


REPAIR_RANK = {"light": 1, "medium": 2, "heavy": 3}


def score_listing(listing: dict, criteria: SearchCriteria) -> tuple[int, list[str]]:
    score = 70
    reasons: list[str] = []

    if listing["price"] > criteria.max_price:
        score -= min(35, int((listing["price"] - criteria.max_price) / 200))
        reasons.append("über Budget")
    elif listing["price"] <= criteria.max_price * 0.75:
        score += 8
    elif listing["price"] <= criteria.max_price:
        score += 4

    if listing["distance_km"] > criteria.max_distance_km:
        score -= 15
        reasons.append("außerhalb Suchradius")

    if listing["year"] < criteria.min_year:
        score -= 8
        reasons.append("älter als Wunschbereich")

    if listing["mileage"] > criteria.max_mileage:
        score -= 12
        reasons.append("hohe Laufleistung")

    if criteria.require_three_point_belt and not listing["three_point_belt"]:
        score -= 24
        reasons.append("3-Punkt-Gurt fehlt/ungeklärt")

    if listing["weight_kg"] > criteria.max_weight_kg:
        score -= 20
        reasons.append("zu hohes Gesamtgewicht")

    if criteria.require_alkoven and listing["body_type"].lower() != "alkoven":
        score -= 25
        reasons.append("kein Alkoven")

    if criteria.preferred_engine and criteria.preferred_engine.lower() not in listing["engine"].lower():
        score -= 8
        reasons.append("Motor nicht bevorzugt")
    else:
        score += 8

    if listing["dry_status"] == "measured_dry":
        score += 8
    elif listing["dry_status"] == "claimed_dry":
        score += 2
    else:
        score -= 6
        reasons.append("Feuchtigkeit ungeklärt")

    if REPAIR_RANK[listing["repair_level"]] > REPAIR_RANK[criteria.repair_tolerance]:
        score -= 14
        reasons.append("zu hoher Reparaturbedarf")
    elif listing["repair_level"] == "light":
        score += 3

    return max(0, min(100, score)), reasons


def matches_hard_filters(listing: dict, criteria: SearchCriteria) -> bool:
    return (
        listing["price"] <= criteria.max_price * 1.15
        and listing["distance_km"] <= criteria.max_distance_km * 1.25
        and listing["weight_kg"] <= criteria.max_weight_kg + 250
        and (not criteria.require_alkoven or listing["body_type"].lower() == "alkoven")
    )
