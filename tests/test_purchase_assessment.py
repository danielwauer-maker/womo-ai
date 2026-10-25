import unittest

from app.scoring import SearchCriteria, assess_listing


class PurchaseAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.criteria = SearchCriteria()

    def test_good_matching_motorhome_scores_high(self):
        item = {
            "price": 8500,
            "year": 1992,
            "mileage": 170000,
            "body_type": "Alkoven",
            "weight_kg": 3400,
            "three_point_belt": True,
            "dry_status": "measured_dry",
            "repair_level": "light",
            "base_make": "Fiat",
            "base_model": "Ducato",
            "engine": "2.5 TD",
            "technical": {"inspection": "04/2027", "gas_inspection": "04/2027"},
        }
        result = assess_listing(item, self.criteria)
        self.assertGreaterEqual(result["score"], 85)
        self.assertEqual(result["verdict"], "sehr interessant")
        self.assertGreaterEqual(result["confidence"], 85)

    def test_moisture_is_a_major_blocker(self):
        item = {
            "price": 9000,
            "body_type": "Alkoven",
            "weight_kg": 3500,
            "three_point_belt": True,
            "dry_status": "unknown",
            "repair_level": "unknown",
            "technical": {"moisture_issue": True},
        }
        result = assess_listing(item, self.criteria)
        self.assertIn("Feuchtigkeits-/Wasserschadenhinweis im Inserat", result["blockers"])
        self.assertEqual(result["verdict"], "kritisch prüfen")

    def test_missing_three_point_belt_is_a_blocker(self):
        item = {
            "price": 7000,
            "body_type": "Alkoven",
            "weight_kg": 3300,
            "three_point_belt": False,
            "dry_status": "measured_dry",
            "repair_level": "light",
        }
        result = assess_listing(item, self.criteria)
        self.assertIn("3-Punkt-Gurt hinten fehlt", result["blockers"])
        self.assertEqual(result["verdict"], "kritisch prüfen")

    def test_overweight_is_a_blocker(self):
        item = {
            "price": 7000,
            "body_type": "Alkoven",
            "weight_kg": 3850,
            "three_point_belt": True,
            "dry_status": "measured_dry",
            "repair_level": "light",
        }
        result = assess_listing(item, self.criteria)
        self.assertIn("zGG über 3,5 t", result["blockers"])

    def test_unknowns_lower_confidence_not_vehicle_score_aggressively(self):
        item = {"price": 9000, "body_type": "Alkoven"}
        result = assess_listing(item, self.criteria)
        self.assertLess(result["confidence"], 50)
        self.assertEqual(result["verdict"], "zu wenig Daten")
        self.assertIn("3-Punkt-Gurt hinten noch prüfen", result["unknowns"])
        self.assertIn("Feuchtigkeit noch messen", result["unknowns"])

    def test_belted_seats_does_not_imply_three_point_belt(self):
        item = {
            "price": 8000,
            "body_type": "Alkoven",
            "technical": {"seats": 6, "belted_seats": 4},
            "three_point_belt": None,
        }
        result = assess_listing(item, self.criteria)
        self.assertIn("3-Punkt-Gurt hinten noch prüfen", result["unknowns"])
        self.assertNotIn("3-Punkt-Gurt hinten bestätigt", result["positives"])


if __name__ == "__main__":
    unittest.main()
