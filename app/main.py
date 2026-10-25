from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .data import LISTINGS
from .scoring import SearchCriteria, matches_hard_filters, score_listing

app = FastAPI(title="Womo AI", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "defaults": SearchCriteria()},
    )


@app.post("/search", response_class=HTMLResponse)
def search(
    request: Request,
    max_price: int = Form(11000),
    max_distance_km: int = Form(300),
    min_year: int = Form(1988),
    max_mileage: int = Form(260000),
    require_three_point_belt: bool = Form(False),
    max_weight_kg: int = Form(3500),
    repair_tolerance: str = Form("medium"),
    preferred_engine: str = Form("2.5"),
    require_alkoven: bool = Form(False),
):
    criteria = SearchCriteria(
        max_price=max_price,
        max_distance_km=max_distance_km,
        min_year=min_year,
        max_mileage=max_mileage,
        require_three_point_belt=require_three_point_belt,
        max_weight_kg=max_weight_kg,
        repair_tolerance=repair_tolerance,
        preferred_engine=preferred_engine.strip(),
        require_alkoven=require_alkoven,
    )

    results = []
    for listing in LISTINGS:
        if not matches_hard_filters(listing, criteria):
            continue
        score, score_reasons = score_listing(listing, criteria)
        results.append({**listing, "score": score, "score_reasons": score_reasons})

    results.sort(key=lambda item: (item["score"], -item["price"]), reverse=True)
    return templates.TemplateResponse(
        "results.html",
        {"request": request, "criteria": criteria, "results": results},
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
