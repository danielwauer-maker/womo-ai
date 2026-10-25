import re
from .scoring import SearchCriteria


def criteria_from_prompt(prompt: str, defaults: SearchCriteria | None = None) -> SearchCriteria:
    c = defaults or SearchCriteria()
    text = (prompt or "").lower()

    price = re.search(r"(?:max(?:imal)?|bis|unter)\s*(\d{1,3}(?:[\.\s]\d{3})?|\d+)\s*(?:€|euro)", text)
    if price:
        c.max_price = int(re.sub(r"\D", "", price.group(1)))

    distance = re.search(r"(?:max(?:imal)?|bis|unter)\s*(\d{2,4})\s*km", text)
    if distance:
        c.max_distance_km = int(distance.group(1))

    year = re.search(r"(?:ab|mindestens)\s*(19\d{2}|20\d{2})", text)
    if year:
        c.min_year = int(year.group(1))

    mileage = re.search(r"(?:max(?:imal)?|bis|unter)\s*(\d{2,3}(?:[\.\s]\d{3})?)\s*km", text)
    if mileage:
        value = int(re.sub(r"\D", "", mileage.group(1)))
        if value > 1000:
            c.max_mileage = value

    if "alkoven" in text:
        c.require_alkoven = True
    if "3-punkt" in text or "dreipunkt" in text or "kindersitz" in text or "kind" in text:
        c.require_three_point_belt = True
    if "3,5 t" in text or "3.5 t" in text or "3500" in text:
        c.max_weight_kg = 3500
    if "2.5 td" in text or "2,5 td" in text:
        c.preferred_engine = "2.5 TD"
    if "reparatur" in text or "basteln" in text or "projekt" in text:
        c.repair_tolerance = "medium"
    return c
