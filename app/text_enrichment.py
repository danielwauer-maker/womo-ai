import re

BASE_VEHICLES = {
    "Fiat": ["Ducato"],
    "Peugeot": ["J5", "Boxer"],
    "Citroen": ["C25", "Jumper"],
    "Citroën": ["C25", "Jumper"],
    "Mercedes": ["Sprinter", "T1", "Bremer"],
    "Ford": ["Transit"],
    "Renault": ["Master", "Trafic"],
    "Iveco": ["Daily"],
}

COACHBUILDERS = [
    "Roller Team", "LMC", "Hymer", "Dethleffs", "Bürstner", "Buerstner", "Knaus", "Hobby",
    "Eura Mobil", "Niesmann + Bischoff", "Niesmann", "Laika", "Ahorn", "Adria",
    "Frankia", "Concorde", "Weinsberg", "Chausson", "Elnagh", "Rimor", "CI",
]


def _number(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _engine_from_text(text: str) -> str | None:
    if not text:
        return None
    patterns = [
        r"\b(\d[\.,]\d\s*(?:l(?:iter)?\s*)?(?:turbo\s*)?diesel)\b",
        r"\b(\d[\.,]\d\s*(?:tdi|td|jtd|hdi|dci|cdi|tdci))\b",
        r"\b(\d[\.,]\d\s*(?:l(?:iter)?\s*)?diesel)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip().replace(",", ".")
            value = re.sub(r"\bliter\b", "l", value, flags=re.I)
            return value

    cc = re.search(r"(?:hubraum|ccm|cm³|cm3)\s*[:\-]?\s*([0-9.\s]{4,6})\s*(?:cm³|cm3|ccm)?", text, re.I)
    diesel = re.search(r"(?:kraftstoff\s*[:\-]?\s*)?diesel\b", text, re.I)
    if cc and diesel:
        value = _number(cc.group(1))
        if value and 1000 <= value <= 8000:
            litres = value / 1000
            return f"{litres:.1f} l Diesel ({value} cm³)"
    return None


def extract_vehicle_identity(primary_text: str, current_title: str = "", fallback_text: str = "") -> dict:
    primary = f"{current_title}\n{primary_text or ''}".strip()
    fallback = fallback_text or ""
    result: dict = {}

    def detect_base(text: str):
        lower = text.lower()
        for make, models in BASE_VEHICLES.items():
            make_variants = [make.lower()]
            if make == "Citroen":
                make_variants.append("citroën")
            if not any(v in lower for v in make_variants):
                continue
            result.setdefault("base_make", "Citroën" if make in {"Citroen", "Citroën"} else make)
            for model in models:
                if re.search(rf"\b{re.escape(model)}\b", text, re.I):
                    result.setdefault("base_model", model)
                    break
            return

    detect_base(primary)
    if not result.get("base_make"):
        detect_base(fallback[:12000])

    for name in COACHBUILDERS:
        if re.search(rf"\b{re.escape(name)}\b", primary, re.I):
            result["coachbuilder"] = "Bürstner" if name == "Buerstner" else name
            break
    if not result.get("coachbuilder"):
        for name in COACHBUILDERS:
            if re.search(rf"\b{re.escape(name)}\b", fallback[:12000], re.I):
                result["coachbuilder"] = "Bürstner" if name == "Buerstner" else name
                break

    coachbuilder = result.get("coachbuilder")
    if coachbuilder:
        variants = [coachbuilder]
        if coachbuilder == "Bürstner":
            variants.append("Buerstner")
        for variant in variants:
            m = re.search(rf"\b{re.escape(variant)}\b\s+([A-Za-z0-9][A-Za-z0-9+\- ]{{0,35}})", primary, re.I)
            if m:
                candidate = re.split(r"(?:mit\s+folgenden|Bj\.?|Baujahr|EZ|,|\||\n|\(|für\s+€)", m.group(1), maxsplit=1, flags=re.I)[0].strip(" -")
                if candidate:
                    result["coach_model"] = candidate[:80]
                break

    engine = _engine_from_text(primary_text or "") or _engine_from_text(current_title or "")
    if engine:
        result["engine"] = engine
    return result


def extract_listing_text(text: str, current_title: str = "") -> dict:
    raw = (text or "").strip()
    lower = raw.lower()
    result: dict = {}

    prices = re.findall(r"(?<!\d)(\d{1,3}(?:[\.\s]\d{3})+|\d{4,6})\s*(?:€|eur)(?:\b|\s|$)", raw, re.I)
    if prices:
        result["price"] = _number(prices[0])

    for pattern in [r"(?:kilometer(?:stand)?|km[- ]?stand)\s*[:\-]?\s*(\d{1,3}(?:[\.\s]\d{3})+|\d{4,7})", r"(\d{1,3}(?:[\.\s]\d{3})+)\s*km\b"]:
        m = re.search(pattern, raw, re.I)
        if m:
            result["mileage"] = _number(m.group(1)); break

    for pattern in [r"(?:erstzulassung|ez|baujahr|bj\.?)\s*[:\-]?\s*(?:\d{1,2}[\/.\-])?(19[7-9]\d|20[0-2]\d)", r"\b(19[8-9]\d|20[0-2]\d)\b"]:
        m = re.search(pattern, raw, re.I)
        if m:
            result["year"] = int(m.group(1)); break

    m = re.search(r"\b(\d{2,3})\s*kW\b", raw, re.I)
    if m:
        result["power_kw"] = int(m.group(1))
    else:
        m = re.search(r"\b(\d{2,3})\s*PS\b", raw, re.I)
        if m: result["power_kw"] = round(int(m.group(1)) * 0.735499)

    m = re.search(r"(?:zul(?:ässiges|\.)?\s*gesamtgewicht|gesamtgewicht|zgg)\s*[:\-]?\s*([0-9]{1,2}(?:[\.\s][0-9]{3})|[0-9]{4})\s*kg", raw, re.I)
    if not m: m = re.search(r"\b(3(?:[\.\s]?[0-9]{3}))\s*kg\b", raw, re.I)
    if m: result["weight_kg"] = _number(m.group(1))

    m = re.search(r"(?:sitzplätze|sitzplaetze|zugelassene\s+sitzplätze)\s*[:\-]?\s*(\d)", raw, re.I)
    if m: result["seats"] = int(m.group(1))
    if "alkoven" in lower: result["body_type"] = "Alkoven"

    if re.search(r"3[ -]?punkt[ -]?gurt", lower):
        if re.search(r"(?:kein|ohne|fehlt|nicht vorhanden).{0,30}3[ -]?punkt[ -]?gurt|3[ -]?punkt[ -]?gurt.{0,30}(?:fehlt|nicht vorhanden)", lower):
            result["three_point_belt"] = False
        else: result["three_point_belt"] = True

    if re.search(r"feuchtigkeitsmessung|feuchtemessung", lower) and re.search(r"trocken|keine feuchtigkeit|ohne befund", lower):
        result["dry_status"] = "measured_dry"
    elif re.search(r"(?:dicht|trocken|keine feuchtigkeit|kein wasserschaden)", lower):
        result["dry_status"] = "claimed_dry"
    elif re.search(r"(?:feuchtigkeit|wasserschaden|undicht|nass|weichstelle)", lower):
        result["dry_status"] = "unknown"

    if re.search(r"(?:motorschaden|getriebeschaden|starker rost|durchgerostet|wasserschaden|massiv feucht|kernsanierung)", lower):
        result["repair_level"] = "heavy"
    elif re.search(r"(?:reparatur|bastler|projekt|defekt|mängel|maengel|rost|elektrik.*(?:offen|machen|defekt))", lower):
        result["repair_level"] = "medium"
    elif re.search(r"(?:keine mängel|keine maengel|kein reparaturbedarf|ohne reparaturbedarf)", lower):
        result["repair_level"] = "light"

    identity = extract_vehicle_identity(raw, current_title=current_title)
    if identity.get("engine"): result["engine"] = identity["engine"]
    if identity.get("coachbuilder"): result["make"] = identity["coachbuilder"]
    elif identity.get("base_make"): result["make"] = identity["base_make"]
    return result
