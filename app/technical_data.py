import json
import re


def extract_technical_data(text: str) -> dict:
    text = text or ""
    data: dict = {}

    def grab(pattern: str, key: str, flags=re.I):
        m = re.search(pattern, text, flags)
        if m:
            value = m.group(1).strip()
            if value:
                data[key] = value

    grab(r"Erstzulassung\s*[:\-]?\s*([^\n\r]+)", "first_registration")
    grab(r"Kraftstoff\s*[:\-]?\s*([^\n\r]+)", "fuel")
    grab(r"Hubraum\s*[:\-]?\s*([\d\.\s]+)\s*cm", "displacement_cc")
    grab(r"Getriebe\s*[:\-]?\s*([^\n\r]+)", "transmission")
    grab(r"Farbe\s*[:\-]?\s*([^\n\r]+)", "color")
    grab(r"Abgasnorm\s*[:\-]?\s*([^\n\r]+)", "emissions_standard")

    if re.search(r"T[ÜU]V/AU\s+neu", text, re.I):
        data["tuev"] = "TÜV/AU neu"
    if re.search(r"Serviceheft\s+gepflegt", text, re.I):
        data["service_history"] = "Serviceheft gepflegt"
    if re.search(r"Austauschmotor", text, re.I):
        data["engine_replaced"] = True
    if re.search(r"technisch\s+wie\s+optisch\s+im\s+tadellosen\s+Zustand", text, re.I):
        data["provider_condition_claim"] = "technisch wie optisch tadellos"

    equipment = []
    candidates = {
        "Klimaanlage": r"\bKlimaanlage\b",
        "Bordcomputer": r"\bBordcomputer\b",
        "Multifunktionslenkrad": r"\bMultifunktionslenkrad\b",
        "Tempomat": r"\bTempomat\b",
        "Radio/Tuner": r"\bRadio/Tuner\b",
        "Rückfahrkamera": r"\bR[üu]ckfahrkamera\b",
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
