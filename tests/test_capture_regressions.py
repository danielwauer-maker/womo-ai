import json
import unittest

from app.extractors.mobile_de import MobileDeExtractor
from app.technical_data import extract_technical_data
from app.text_enrichment import extract_vehicle_identity


class CaptureRegressionTests(unittest.TestCase):
    def test_mobile_title_price_wins(self):
        result = MobileDeExtractor().extract(
            title="Was hältst du von diesem Ford für 37.990 € in Leipzig bei mobile.de?",
            description="- Abgasnorm: Euro 5\n-Erstzulassung:18.05.2015\n- Kraftstoff: Diesel",
            page_text="1 / 26",
            structured_data="",
            image_urls_json=json.dumps([]),
        )
        self.assertEqual(result.fields.get("price"), 37990)
        self.assertEqual(result.signals.get("reported_image_count"), 26)

    def test_mobile_bullet_labels_are_parsed(self):
        technical = extract_technical_data(
            "-Erstzulassung:18.05.2015\n"
            "- Kraftstoff: Diesel\n"
            "- Hubraum: 2198 cm³\n"
            "- Getriebe: Schaltgetriebe\n"
            "- Sitzplätze: 4\n"
            "-Zulässiges Gesamtgewicht: 3.500 kg\n"
            "- Farbe: Weiß\n"
            "- Abgasnorm: Euro 5\n"
            "TÜV/AU neu\nServiceheft gepflegt\nAustauschmotor"
        )
        self.assertEqual(technical.get("first_registration"), "18.05.2015")
        self.assertEqual(technical.get("fuel"), "Diesel")
        self.assertEqual(technical.get("displacement_cc"), 2198)
        self.assertEqual(technical.get("transmission"), "Schaltgetriebe")
        self.assertEqual(technical.get("seats"), 4)
        self.assertEqual(technical.get("gross_weight_kg"), 3500)
        self.assertEqual(technical.get("color"), "Weiß")
        self.assertEqual(technical.get("emissions_standard"), "Euro 5")
        self.assertEqual(technical.get("inspection"), "neu")

    def test_combined_tuev_and_gas_date(self):
        technical = extract_technical_data("TÜV & Gasprüfung bis 04/2027")
        self.assertEqual(technical.get("inspection"), "04/2027")
        self.assertEqual(technical.get("gas_inspection"), "04/2027")

    def test_belted_seats_label(self):
        technical = extract_technical_data("Sitze mit Gurt\n4")
        self.assertEqual(technical.get("seats"), 4)
        self.assertEqual(technical.get("belted_seats"), 4)

    def test_lmc_liberty_6400_model(self):
        identity = extract_vehicle_identity(
            "Fiat Ducato LMC Liberty 6400 (Baujahr 1991), 2,5 l Turbo Diesel",
            current_title="Fiat ducato LMC Liberty Bj.1991 -Projektaufgabe aufgrund Zeit",
        )
        self.assertEqual(identity.get("coachbuilder"), "LMC")
        self.assertEqual(identity.get("coach_model"), "Liberty 6400")

    def test_lmc_6400_does_not_absorb_engine(self):
        identity = extract_vehicle_identity(
            "Fiat Ducato 280 Wohnmobil LMC 6400 2,5TD 95PS",
            current_title="Fiat Ducato 280 Wohnmobil LMC 6400 2,5TD 95PS",
        )
        self.assertEqual(identity.get("coach_model"), "6400")


if __name__ == "__main__":
    unittest.main()
