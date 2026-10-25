# Golden Fixtures

Golden Fixtures sind bestätigte Capture-Snapshots mit erwarteten Extraktionsergebnissen.

Jede Fixture ist eine JSON-Datei mit diesem Schema:

```json
{
  "source": "mobile.de",
  "name": "mobile-48362590386592",
  "snapshot": {
    "title": "...",
    "description": "...",
    "page_text": "...",
    "structured_data": "[]",
    "image_urls_json": "[]"
  },
  "expected": {
    "fields": {
      "price": 37990,
      "year": 2015,
      "mileage": 113500,
      "power_kw": 114,
      "seats": 4,
      "weight_kg": 3500
    },
    "identity": {
      "base_make": "Ford",
      "base_model": "Transit",
      "coachbuilder": "Roller Team",
      "coach_model": "275"
    }
  }
}
```

Nur Felder, die in `expected` stehen, werden als verbindlich betrachtet. Unbekannte oder auf dem Portal nicht veröffentlichte Werte bleiben bewusst offen.

Workflow:

1. Capture durchführen.
2. Review-Artefakt gegen die Originalanzeige prüfen.
3. Nach bestätigtem Abgleich daraus eine Golden Fixture erzeugen.
4. Parser-Änderungen müssen alle Golden Fixtures weiterhin erfüllen.
