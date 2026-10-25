import json
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Listing
from app.review_routes import _review_payload


def main() -> None:
    out_dir = Path("/data/review-artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        listings = db.scalars(select(Listing).order_by(Listing.updated_at.desc())).all()
        items = [_review_payload(row) for row in listings]

    index = {
        "schema_version": 1,
        "count": len(items),
        "items": [
            {
                "id": item["id"],
                "source": item["source"],
                "title": item["title"],
                "original_url": item["original_url"],
                "quality": item["quality"],
                "capture_count": item["capture_count"],
                "last_capture_at": item["last_capture_at"],
            }
            for item in items
        ],
    }

    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in items:
        filename = f"listing-{item['id']}.json"
        (out_dir / filename).write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(items)} review artifact(s) to {out_dir}")


if __name__ == "__main__":
    main()
