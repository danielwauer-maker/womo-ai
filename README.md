# Womo AI

Erstes lauffähiges MVP eines KI-gestützten Wohnmobilfinders.

## Was V0.1 kann

- persönliches Suchprofil mit Budget, Radius, Baujahr, Laufleistung und Gewicht
- Priorisierung für Alkoven und 3-Punkt-Gurt
- Motorpräferenz und Reparatur-Toleranz
- 100-Punkte-WomoScore
- Ergebnisseite mit Stärken, Risiken und offenen Punkten
- responsive Oberfläche
- Seed-Angebote als Platzhalter für echte Collector/APIs
- Health-Endpoint und einfache Scoring-Tests

## Lokal starten

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Dann: http://127.0.0.1:8000

## Tests

```bash
pytest
```

## Docker

```bash
docker build -t womo-ai .
docker run --rm -p 8000:8000 womo-ai
```

## Nächste Ausbaustufe (V0.2)

1. PostgreSQL + SQLAlchemy + Alembic
2. Listing-/Source-Modell und Preis-Historie
3. erster erlaubter Collector/API-Adapter
4. URL-Import für einzelne Inserate
5. KI-Textanalyse und strukturierte Risikoextraktion
6. Bildanalyse und Bildergalerie
7. Dublettenerkennung
8. Suchprofile speichern + Alerts

> Hinweis: Marktplatzdaten werden nur über erlaubte APIs, Feeds oder explizit zulässige Importwege angebunden. Plattform-Schutzmaßnahmen werden nicht umgangen.
