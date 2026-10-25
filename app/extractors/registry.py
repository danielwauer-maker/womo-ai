from .autoscout24 import AutoScout24Extractor
from .base import BaseExtractor, ExtractionResult
from .caraworld import CaraworldExtractor
from .kleinanzeigen import KleinanzeigenExtractor
from .mobile_de import MobileDeExtractor


EXTRACTORS = {
    "mobile.de": MobileDeExtractor(),
    "Kleinanzeigen": KleinanzeigenExtractor(),
    "AutoScout24": AutoScout24Extractor(),
    "Caraworld": CaraworldExtractor(),
}


def extract_snapshot(source: str, *, title: str, description: str, page_text: str, structured_data: str, image_urls_json: str) -> ExtractionResult:
    extractor = EXTRACTORS.get(source, BaseExtractor())
    return extractor.extract(
        title=title,
        description=description,
        page_text=page_text,
        structured_data=structured_data,
        image_urls_json=image_urls_json,
    )
