import re

MAKE_NAMES = [
    "Fiat", "Peugeot", "Citroen", "Mercedes", "Ford", "Renault", "Iveco",
    "LMC", "Hymer", "Dethleffs", "Buerstner", "Bürstner", "Knaus", "Hobby",
    "Eura Mobil", "Niesmann", "Laika", "Ahorn", "Adria", "Frankia", "Concorde"
]


def _number(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def extract_listing_text(text: str, current_title: str = "") -> dict:
    """Best-effort extraction from text supplied by the user.

    The original text remains the source of truth. Unknown values stay unknown.
    """
    raw = (text or "").strip()
    lower = raw.lower()
    result: dict = {}

    # Price: prefer values explicitly followed by EUR / €.
    prices = re.findall(r"(?<!\d)(\d{1,3}(?:[\.\s]\d{3})+|\d{4,6})\s*(?:€|eur)\b?", raw, re.I)
    if prices:
        result["price"] = _number(prices[0])

    # Mileage.
    mileage_patterns = [
        r"(?:kilometer(?:stand)?|km[- ]?stand)\s*[:\-]?\s*(\d{1,3}(?:[\.\s]\d{3})+|\d{4,6})",
        r"(\d{1,3}(?:[\.\s]\d{3})+)\s*km\b",
    ]
    for pattern in mileage_patterns:
        m = re.search(pattern, raw, re.I)
        if m:
            result["mileage"] = _number(m.group(1))
            break

    # Year / first registration.
    year_patterns = [
        r"(?:erstzulassung|ez|baujahr|bj\.?)\s*[:\-]?\s*(?:\d{1,2}[\/.\-])?(19[7-9]\d|20[0-2]\d)",
        r"\b(19[8-9]\d|20[0-2]\d)\b",
    ]
    for pattern in year_patterns:
        m = re.search(pattern, raw, re.I)
        if m:
            result["year"] = int(m.group(1))
            break

    # Power.
    m = re.search(r"\b(\d{2,3})\s*kW\b", raw, re.I)
    if m:
        result["power_kw"] = int(m.group(1))
    else:
        m = re.search(r"\b(\d{2,3})\s*PS\b", raw, re.I)
        if m:
            result["power_kw"] = round(int(m.group(1)) * 0.735499)

    # Weight.
    m = re.search(r"(?:zul(?:ässiges|\.)?\s*gesamtgewicht|gesamtgewicht|zgg)\s*[:\-]?\s*(\d{4})\s*kg", raw, re.I)
    if not m:
        m = re.search(r"\b(3[0-9]{3})\s*kg\b", raw, re.I)
    if m:
        result["weight_kg"] = int(m.group(1))

    # Seats.
    m = re.search(r"(?:sitzplätze|sitzplaetze|zugelassene\s+sitzplätze)\s*[:\-]?\s*(\d)", raw, re.I)
    if m:
        result["seats"] = int(m.group(1))

    # Body type.
    if "alkoven" in lower:
        result["body_type"] = "Alkoven"

    # Three-point belt. Do not infer absence merely from missing text.
    if re.search(r"3[ -]?punkt[ -]?gurt", lower):
        if re.search(r"(?:kein|ohne|fehlt|nicht vorhanden).{0,30}3[ -]?punkt[ -]?gurt|3[ -]?punkt[ -]?gurt.{0,30}(?:fehlt|nicht vorhanden)", lower):
            result["three_point_belt"] = False
        else:
            result["three_point_belt"] = True

    # Moisture / dry claims.
    if re.search(r"feuchtigkeitsmessung|feuchtemessung", lower) and re.search(r"trocken|keine feuchtigkeit|ohne befund", lower):
        result["dry_status"] = "measured_dry"
    elif re.search(r"(?:dicht|trocken|keine feuchtigkeit|kein wasserschaden)", lower):
        result["dry_status"] = "claimed_dry"
    elif re.search(r"(?:feuchtigkeit|wasserschaden|undicht|nass|weichstelle)", lower):
        result["dry_status"] = "unknown"

    # Repair level (conservative).
    if re.search(r"(?:motorschaden|getriebeschaden|starker rost|durchgerostet|wasserschaden|massiv feucht|kernsanierung)", lower):
        result["repair_level"] = "heavy"
    elif re.search(r"(?:reparatur|bastler|projekt|defekt|mängel|maengel|rost|elektrik.*(?:offen|machen|defekt))", lower):
        result["repair_level"] = "medium"
    elif re.search(r"(?:gepflegt|fahrbereit|sofort einsatzbereit|keine mängel|keine maengel)", lower):
        result["repair_level"] = "light"

    # Engine: capture common diesel descriptions.
    engine_patterns = [
        r"\b(\d[\.,]\d\s*(?:tdi|td|d|jtd|hdi))\b",
        r"\b(2[\.,][0-9]\s*(?:turbo\s*)?diesel)\b",
    ]
    for pattern in engine_patterns:
        m = re.search(pattern, raw, re.I)
        if m:
            result["engine"] = re.sub(r"\s+", " ", m.group(1)).strip().replace(",", ".")
            break

    # Make: only when a known name is explicitly present.
    combined = f"{current_title} {raw[:1200]}".lower()
    for make in MAKE_NAMES:
        if make.lower() in combined:
            result["make"] = make.replace("Buerstner", "Bürstner")
            break

    return result
