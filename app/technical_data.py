import json
import re


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip(" \t:-"))


def _int_value(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def extract_technical_data(text: str) -> dict:
    text = text or ""
    data: dict = {}

    def grab(pattern: str, key: str, flags=re.I):
        m = re.search(pattern, text, flags)
        if m:
            value = _clean(m.group(1))
            if value:
                data[key] = value

    # Core technical facts. Patterns deliberately accept portal label variations.
    grab(r"(?:Erstzulassung|EZ)\s*[:\-]?\s*([^\n\r]+)", "first_registration")
    grab(r"Kraftstoff(?:art)?\s*[:\-]?\s*([^\n\r]+)", "fuel")
    grab(r"Hubraum\s*[:\-]?\s*([\d\.\s]+)\s*(?:cm³|cm3|ccm)", "displacement_cc")
    grab(r"Getriebe(?:art)?\s*[:\-]?\s*([^\n\r]+)", "transmission")
    grab(r"(?:Außen)?Farbe\s*[:\-]?\s*([^\n\r]+)", "color")
    grab(r"(?:Abgasnorm|Schadstoffklasse|Emissionsklasse)\s*[:\-]?\s*([^\n\r]+)", "emissions_standard")
    grab(r"(?:Umweltplakette|Plakette)\s*[:\-]?\s*([^\n\r]+)", "environmental_badge")
    grab(r"(?:HU|Hauptuntersuchung|TÜV)\s*[:\-]?\s*([^\n\r]+)", "inspection")
    grab(r"(?:Gasprüfung|Gaspr[üu]fung)\s*[:\-]?\s*([^\n\r]+)", "gas_inspection")
    grab(r"(?:Antrieb|Antriebsart)\s*[:\-]?\s*([^\n\r]+)", "drive")

    # Dimensions and weights.
    for key, patterns in {
        "length_cm": [r"Länge\s*[:\-]?\s*([\d\.]+)\s*cm", r"Länge\s*[:\-]?\s*([\d\.,]+)\s*m\b"],
        "width_cm": [r"Breite\s*[:\-]?\s*([\d\.]+)\s*cm", r"Breite\s*[:\-]?\s*([\d\.,]+)\s*m\b"],
        "height_cm": [r"Höhe\s*[:\-]?\s*([\d\.]+)\s*cm", r"Höhe\s*[:\-]?\s*([\d\.,]+)\s*m\b"],
        "empty_weight_kg": [r"(?:Leergewicht|Masse in fahrbereitem Zustand)\s*[:\-]?\s*([\d\.\s]+)\s*kg"],
        "gross_weight_kg": [r"(?:Zulässiges Gesamtgewicht|Gesamtgewicht|zGG)\s*[:\-]?\s*([\d\.\s]+)\s*kg"],
        "sleeping_places": [r"(?:Schlafplätze|Schlafplaetze)\s*[:\-]?\s*(\d+)"],
        "seats": [r"(?:Sitzplätze|Sitzplaetze)\s*[:\-]?\s*(\d+)"],
    }.items():
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if not m:
                continue
            raw = m.group(1).replace(",", ".")
            if key in {"length_cm", "width_cm", "height_cm"} and re.search(r"\bm\b", m.group(0), re.I):
                try:
                    data[key] = round(float(raw) * 100)
                except ValueError:
                    pass
            else:
                value = _int_value(raw)
                if value is not None:
                    data[key] = value
            break

    # Maintenance / history.
    if re.search(r"T[ÜU]V/AU\s+neu|HU\s+neu|T[ÜU]V\s+neu", text, re.I):
        data["tuev"] = "neu"
    if re.search(r"Serviceheft\s+gepflegt|scheckheft(?:gepflegt)?", text, re.I):
        data["service_history"] = "gepflegt"
    if re.search(r"Austauschmotor|Motor\s+(?:wurde\s+)?(?:ersetzt|ausgetauscht)", text, re.I):
        data["engine_replaced"] = True
    if re.search(r"(?:Motor|Triebwerk).{0,30}(?:generalüberholt|überholt|revidiert)", text, re.I | re.S):
        data["engine_overhauled"] = True
    if re.search(r"H[- ]Kennzeichen|Oldtimerzulassung|Oldtimer\b", text, re.I):
        data["historic_vehicle"] = True

    # Provider claims must stay separate from objective state.
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

    # Damage / moisture findings are decision-critical. Preserve evidence snippets.
    risk_patterns = {
        "moisture": [
            r"[^\n\r]{0,80}(?:Feuchtigkeitsstelle(?:n)?|Feuchtigkeit|Wasserschaden|undicht|Nässe|Nässchaden)[^\n\r]{0,120}",
            r"[^\n\r]{0,80}(?:weich(?:e|er|es)? Stelle|Weichstelle)[^\n\r]{0,120}",
        ],
        "rust": [r"[^\n\r]{0,70}(?:Rost|Korrosion|durchgerostet)[^\n\r]{0,120}"],
        "accident": [r"[^\n\r]{0,70}(?:Unfallschaden|Unfallfahrzeug|beschädigt)[^\n\r]{0,120}"],
        "defect": [r"[^\n\r]{0,70}(?:defekt|Mangel|Mängel|reparaturbedürftig|Bastlerfahrzeug)[^\n\r]{0,120}"],
    }
    findings = []
    categories = []
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
