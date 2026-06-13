"""Conversion d'un :class:`ExtractionResult` en ``ContentBlock`` openingestion.

Glue entre la couche d'extraction (façon Onyx) et le ``SentenceChunker``
d'openingestion. Préserve le ``page_idx`` de chaque segment/image et réindexe
``block_index`` / ``reading_order`` après tri stable par page (les images d'une
page atterrissent après son texte, comme l'ancien ``_build_and_merge_blocks``).
"""
from __future__ import annotations

from .extract import ExtractionResult


def extraction_to_content_blocks(
    result: ExtractionResult,
    image_descriptions: list[tuple[str, int]],
):
    """Construit la liste de ``ContentBlock`` page-aware pour le chunker.

    Args:
        result: résultat d'extraction (segments texte + images + metadata).
        image_descriptions: ``[(description, page_idx), ...]`` issues de l'étape
            vision (placeholders si la vision refinery est désactivée).

    Returns:
        ``list[ContentBlock]`` réindexée, en ordre de lecture.
    """
    from openingestion.document import ContentBlock, BlockKind

    blocks: list[ContentBlock] = []

    for seg in result.segments:
        if seg.is_title:
            kind = BlockKind.TITLE
        elif seg.is_table:
            kind = BlockKind.TABLE
        else:
            kind = BlockKind.TEXT
        blocks.append(
            ContentBlock(
                kind=kind,
                text=seg.text,
                page_idx=seg.page_idx,
                bbox=seg.bbox if seg.bbox is not None else [0, 0, 0, 0],
                title_level=seg.title_level if seg.is_title else 0,
            )
        )

    for description, page_idx in image_descriptions:
        blocks.append(
            ContentBlock(
                kind=BlockKind.IMAGE,
                text=description,
                page_idx=page_idx,
                bbox=[0, 0, 0, 0],
            )
        )

    # Tri stable par page : conserve l'ordre d'insertion intra-page (texte puis
    # images), puis réindexe pour des indices propres et contigus.
    blocks.sort(key=lambda b: b.page_idx)
    return [
        ContentBlock(
            kind=b.kind,
            text=b.text,
            page_idx=b.page_idx,
            bbox=b.bbox,
            title_level=b.title_level,
            html=b.html,
            img_path=b.img_path,
            captions=list(b.captions),
            footnotes=list(b.footnotes),
            block_index=i,
            reading_order=i,
            raw=dict(b.raw),
        )
        for i, b in enumerate(blocks)
    ]
