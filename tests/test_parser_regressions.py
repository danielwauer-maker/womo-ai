import unittest

from app.technical_data import extract_technical_data
from app.text_enrichment import extract_listing_text
from app.extractors.autoscout24 import _normalize_autoscout_images
from app.extractors.caraworld import _normalize_caraworld_images
from app.extractors.kleinanzeigen import _normalize_kleinanzeigen_images


class ParserRegressionTests(unittest.TestCase):
    def test_tuev_year_is_not_vehicle_year(self):
        text = "TÜV/AU 06/2027\nH-Kennzeichen\n203.700 km"
        data = extract_listing_text(text, current_title="Fiat Ducato 280 Wohnmobil LMC 6400")
        self.assertNotEqual(data.get("year"), 2027)

    def test_explicit_vehicle_year_wins(self):
        text = "Baujahr 1991\nTÜV bis 04/2027"
        data = extract_listing_text(text)
        self.assertEqual(data.get("year"), 1991)

    def test_historic_negation(self):
        data = extract_technical_data("Kein H-Kennzeichen: wegen Umbauten keine Oldtimer-Zulassung")
        self.assertIs(data.get("historic_vehicle"), False)

    def test_historic_positive(self):
        data = extract_technical_data("H-Kennzeichen\nMotor generalüberholt")
        self.assertIs(data.get("historic_vehicle"), True)
        self.assertIs(data.get("engine_overhauled"), True)

    def test_labels_do_not_match_substrings(self):
        text = "Schufa-neutral\nFarbe und Innenausstattung\nVersandart"
        data = extract_technical_data(text)
        self.assertNotIn("inspection", data)
        self.assertNotIn("color", data)
        self.assertNotIn("drive", data)

    def test_empty_weight_is_not_gross_weight(self):
        data = extract_technical_data("Leergewicht\n3.010 kg\nZulässiges Gesamtgewicht\n3.500 kg")
        self.assertEqual(data.get("empty_weight_kg"), 3010)
        self.assertEqual(data.get("gross_weight_kg"), 3500)

    def test_moisture_is_preserved(self):
        data = extract_technical_data("Feuchtigkeitsstellen in der Garage (siehe Bilder)")
        self.assertIs(data.get("moisture_issue"), True)
        self.assertIn("moisture", data.get("risk_categories", []))

    def test_belted_seats_from_prose(self):
        data = extract_technical_data("Eingetragen sind 6 Sitze wovon 4 Stück mit Gurte sind")
        self.assertEqual(data.get("seats"), 6)
        self.assertEqual(data.get("belted_seats"), 4)

    def test_autoscout_image_dedup(self):
        urls = [
            "https://prod.pictures.autoscout24.net/listing-images/id_photo.jpg/120x90.jpg",
            "https://prod.pictures.autoscout24.net/listing-images/id_photo.jpg/1920x1080.webp",
            "https://www.autoscout24.de/assets/logo.svg",
        ]
        self.assertEqual(len(_normalize_autoscout_images(urls)), 1)

    def test_caraworld_image_dedup(self):
        urls = [
            "https://cdn.caraworld.com/bilder/i/028/343/924/28343924-3-220-0.webp",
            "https://cdn.caraworld.com/bilder/i/028/343/924/28343924-3-728-0.webp",
            "https://cdn.caraworld.com/app/i/logo.svg",
        ]
        self.assertEqual(len(_normalize_caraworld_images(urls)), 1)

    def test_kleinanzeigen_image_filter(self):
        urls = [
            "https://img.kleinanzeigen.de/api/v1/prod-ads/images/aa/photo?rule=$_59.AUTO",
            "https://img.kleinanzeigen.de/api/v1/prod-ads/images/aa/photo?rule=$_0.AUTO",
            "https://bat.bing.com/action/0",
        ]
        self.assertEqual(len(_normalize_kleinanzeigen_images(urls)), 1)


if __name__ == "__main__":
    unittest.main()
