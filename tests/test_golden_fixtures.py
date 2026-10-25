import json
import unittest
from pathlib import Path

from app.extractors import extract_snapshot


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "golden"


class GoldenFixtureTests(unittest.TestCase):
    def test_golden_fixtures(self):
        fixture_files = sorted(FIXTURE_DIR.glob("*.json"))
        for path in fixture_files:
            with self.subTest(fixture=path.name):
                fixture = json.loads(path.read_text(encoding="utf-8"))
                snapshot = fixture["snapshot"]
                result = extract_snapshot(
                    fixture["source"],
                    title=snapshot.get("title", ""),
                    description=snapshot.get("description", ""),
                    page_text=snapshot.get("page_text", ""),
                    structured_data=snapshot.get("structured_data", "[]"),
                    image_urls_json=snapshot.get("image_urls_json", "[]"),
                )

                for key, expected in fixture.get("expected", {}).get("fields", {}).items():
                    self.assertEqual(result.fields.get(key), expected, f"{path.name}: fields.{key}")
                for key, expected in fixture.get("expected", {}).get("identity", {}).items():
                    self.assertEqual(result.identity.get(key), expected, f"{path.name}: identity.{key}")


if __name__ == "__main__":
    unittest.main()
