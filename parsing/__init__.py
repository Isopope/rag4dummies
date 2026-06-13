"""Couche de parsing fallback robuste, inspirée de la file_processing d'Onyx."""
from .blocks import extraction_to_content_blocks
from .extract import (
    ExtractedImage,
    ExtractionResult,
    PageSegment,
    SUPPORTED_EXTENSIONS,
    extract_document,
)

__all__ = [
    "ExtractedImage",
    "ExtractionResult",
    "PageSegment",
    "SUPPORTED_EXTENSIONS",
    "extract_document",
    "extraction_to_content_blocks",
]
