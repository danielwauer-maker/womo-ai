import json
import re


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip(" \t:-"))


def _int_value(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _label_value(lines: list[str], labels: tuple[str, ...]) -> str | None:
    normalized = [line.strip() for line in lines]
    for index, line in enumerate(normalized):
        for label in labels:
            m = re.match(rf"^{re.escape(label)}\s*[:\-]?\s*(.*)$", line, re.I)
            if not m:
                continue
            inline = _clean(m.group(1))
            if inline:
                return inline
            if index + 1 < len(normalized):
                nxt = _clean(normalized[index + 1])
                if nxt:
                    return nxt
    return None


def _valid_month_year(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"\b(0?[1-9]|1[0-2])[./-](19\d{2}|20\d{2})\b", value)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    m = re.search(r"\b([0-3]?\d[./-](?:0?[1-9]|1[0-2])[./-](?:19\d{2}|20\d{2}))\b", value)
    return m.group(1) if m else None


def extract_technical_data(text: str) -> dict:
    text = text or ""
    lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]
    data: dict = {}

    first_registration = _label_value(lines, ("Erstzulassung", "EZ"))
    if first_registration:
        data["first_registration"] = first_registration

    fuel = _label_value(lines, ("Kraftstoff", "Kraftstoffart"))
    if fuel and re.search(r"\b(Diesel|Benzin|Elektro|Hybrid|Gas|LPG|CNG)\b", fuel, re.I):
        data["fuel"] = _clean(fuel)

    displacement = _label_value(lines, ("Hubraum",))
    if displacement:
        value = _int_value(displacement)
        if value and 500 <= value <= 10000:
            data["displacement_cc"] = value

    transmission = _label_value(lines, ("Getriebe", "Getriebeart"))
    if transmission and re.search(r"Schaltgetriebe|Automatik|Halbautomatik|manuell", transmission, re.I):
        data["transmission"] = _clean(transmission)

    color = _label_value(lines, ("Außenfarbe", "Farbe"))
    if color and len(color) <= 80 and not re.search(r"Innenausstattung|und Innen", color, re.I):
        data["color"] = _clean(color)

    emissions = _label_value(lines, ("Abgasnorm", "Schadstoffklasse", "Emissionsklasse"))
    if emissions and re.search(r"Euro\s*[0-9IVX]+", emissions, re.I):
        data["emissions_standard"] = _clean(emissions)

    badge = _label_value(lines, ("Umweltplakette", "Plakette"))
    if badge and len(badge) <= 50:
        data["environmental_badge"] = _clean(badge)

    inspection = _label_value(lines, ("HU", "Hauptuntersuchung", "TÜV"))
    inspection_date = _valid_month_year(inspection)
    if inspection_date:
        data["inspection"] = inspection_date
    elif re.search(r"T[ÜU]V/AU\s+neu|HU\s+neu|T[ÜU]V\s+neu", text, re.I):
        data["inspection"] = "neu"

    gas = _label_value(lines, ("Gasprüfung", "Gaspruefung"))
    gas_date = _valid_month_year(gas)
    if gas_date:
        data["gas_inspection"] = gas_date

    drive = _label_value(lines, ("Antrieb", "Antriebsart"))
    if drive and re.search(r"Frontantrieb|Heckantrieb|Allrad|4x4", drive, re.I):
        data["drive"] = _clean(drive)

    # Dimensions and weights: only explicit labels count.
    labelled_numeric = {
        "length_cm": ("Gesamtlänge", "Länge"),
        "width_cm": ("Gesamtbreite", "Breite"),
        "height_cm": ("Gesamthöhe", "Höhe"),
        "empty_weight_kg": ("Leergewicht", "Masse in fahrbereitem Zustand"),
        "gross_weight_kg": ("Zulässiges Gesamtgewicht", "Gesamtgewicht", "zGG"),
        "sleeping_places": ("Schlafplätze", "Schlafplaetze", "Betten"),
        "seats": ("Sitzplätze", "Sitzplaetze", "Sitze"),
    }
    for key, labels in labelled_numeric.items():
        value = _label_value(lines, labels)
        if not value:
            continue
        if key in {"sleeping_places", "seats"}:
            m = re.search(r"\b(\d{1,2})\b", value)
            if m:
                data[key] = int(m.group(1))
            continue
        m = re.search(r"([\d.,]+)\s*(cm|m|kg)\b", value, re.I)
        if not m:
            continue
        raw, unit = m.group(1).replace(",", "."), m.group(2).lower()
        try:
            if unit == "m" and key in {"length_cm", "width_cm", "height_cm"}:
                data[key] = round(float(raw) * 100)
            else:
                parsed = _int_value(raw)
                if parsed is not None:
                    data[key] = parsed
        except ValueError:
            pass

    # Common prose fallbacks limited to explicit phrases.
    m = re.search(r"\b(\d+)\s+Sitze\b.*?\b(\d+)\s+(?:Stück\s+)?mit\s+Gurt", text, re.I | re.S)
    if m and "seats" not in data:
        data["seats"] = int(m.group(1))
        data["belted_seats"] = int(m.group(2))
    m = re.search(r"Schlafmöglichkeiten\s+(?:auch\s+)?für\s+(\d+)\s+Person", text, re.I)
    if m and "sleeping_places" not in data:
        data["sleeping_places"] = int(m.group(1))

    if re.search(r"Serviceheft\s+gepflegt|scheckheft(?:gepflegt)?", text, re.I):
        data["service_history"] = "gepflegt"
    if re.search(r"Austauschmotor|Motor\s+(?:wurde\s+)?(?:ersetzt|ausgetauscht)", text, re.I):
        data["engine_replaced"] = True
    if re.search(r"(?:Motor|Triebwerk).{0,30}(?:generalüberholt|überholt|revidiert)", text, re.I | re.S):
        data["engine_overhauled"] = True

    if re.search(r"\b(?:kein|ohne)\s+H[- ]Kennzeichen\b|keine\s+Oldtimer[- ]?Zulassung", text, re.I):
        data["historic_vehicle"] = False
    elif re.search(r"\bH[- ]Kennzeichen\b|Oldtimerzulassung|\bOldtimer\b", text, re.I):
        data["historic_vehicle"] = True

    # Provider claims must stay separate from objective state and only use primary wording.
    condition_patterns = [
        r"technisch\s+wie\s+optisch\s+(?:im\s+)?tadellosen\s+Zustand",
        r"(?:sehr\s+)?gepflegter\s+Zustand",
        r"technisch\s+(?:und|&)\s+optisch\s+sehr\s+gut",
    ]
    for pattern in condition_patterns:
        m = re.search(pattern, text, re.I)
        if m:
            data["provider_condition_claim"] = _clean(m.group(0))
            break

    risk_patterns = {
        "moisture": [
            r"[^\n\r]{0,80}(?:Feuchtigkeitsstelle(?:n)?|Feuchtigkeit|Wasserschaden|undicht|Nässe|Nässchaden)[^\n\r]{0,120}",
            r"[^\n\r]{0,80}(?:weich(?:e|er|es)? Stelle|Weichstelle)[^\n\r]{0,120}",
        ],
        "rust": [r"[^\n\r]{0,70}(?:Rost|Korrosion|durchgerostet)[^\n\r]{0,120}"],
        "accident": [r"[^\n\r]{0,70}(?:Unfallschaden|Unfallfahrzeug|beschädigt)[^\n\r]{0,120}"],
        "defect": [r"[^\n\r]{0,70}(?:defekt|Mangel|Mängel|reparaturbedürftig|Bastlerfahrzeug)[^\n\r]{0,120}"],
    }
    findings, categories = [], []
    for category, patterns in risk_patterns.items():
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                snippet = _clean(m.group(0))[:240]
                if snippet and snippet not in findings:
                    findings.append(snippet)
                categories.append(category)
                break
    if findings:
        data["condition_findings"] = findings
        data["risk_categories"] = sorted(set(categories))
    if "moisture" in categories:
        data["moisture_issue"] = True

    equipment = []
    candidates = {
        "Klimaanlage": r"\bKlimaanlage\b|\bKlimaautomatik\b",
        "Standheizung": r"\bStandheizung\b",
        "Bordcomputer": r"\bBordcomputer\b",
        "Multifunktionslenkrad": r"\bMultifunktionslenkrad\b",
        "Tempomat": r"\bTempomat\b|\bCruise Control\b",
        "Radio/Tuner": r"\bRadio(?:/Tuner)?\b",
        "Rückfahrkamera": r"\bR[üu]ckfahrkamera\b",
        "Fahrradträger": r"\bFahrradtr[äa]ger\b",
        "Markise": r"\bMarkise\b",
        "Solar": r"\bSolar(?:anlage|panel|modul)?\b",
        "Sat-TV": r"\bSAT(?:-Anlage)?\b|\bSatellitenanlage\b",
        "WC": r"\bWC\b|\bToilette\b",
        "Dusche": r"\bDusche\b",
        "Küche": r"\bK[üu]che\b|\bK[üu]chenzeile\b",
        "Fußbodenheizung": r"\bFu[ßss]bodenheizung\b",
        "Heckleiter": r"\bHeckleiter\b",
    }
    for name, pattern in candidates.items():
        if re.search(pattern, text, re.I):
            equipment.append(name)
    if equipment:
        data["equipment"] = equipment

    return data


def dumps_technical_data(data: dict) -> str:
    return json.dumps(data or {}, ensure_ascii=False, sort_keys=True)


def loads_technical_data(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
