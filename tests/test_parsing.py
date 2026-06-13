"""Tests de la couche de parsing fallback (module ``parsing/``) façon Onyx."""
from __future__ import annotations

import pytest

import ingestor
from parsing import extract_document, extraction_to_content_blocks
from parsing.extract import (
    ExtractedImage,
    ExtractionResult,
    PageSegment,
    _extract_xlsx,
    _markdown_to_segments,
    _sniff_image_mime,
)


# ── Markdown → segments ────────────────────────────────────────────────────────

def test_markdown_groups_table_drops_separator_and_detects_titles():
    md = (
        "# Titre principal\n"
        "\n"
        "Un paragraphe d'introduction.\n"
        "\n"
        "| Col A | Col B |\n"
        "|-------|-------|\n"
        "| 1     | 2     |\n"
        "| 3     | 4     |\n"
    )
    segments = _markdown_to_segments(md)

    titles = [s for s in segments if s.is_title]
    tables = [s for s in segments if s.is_table]
    texts = [s for s in segments if not s.is_title and not s.is_table]

    assert [t.text for t in titles] == ["Titre principal"]
    assert titles[0].title_level == 1
    assert [t.text for t in texts] == ["Un paragraphe d'introduction."]
    # Une seule table, lignes de données regroupées, ligne de séparation supprimée.
    assert len(tables) == 1
    table_lines = tables[0].text.splitlines()
    assert len(table_lines) == 3  # header + 2 lignes de données
    assert not any(set(line) <= set("|-: ") for line in table_lines)


# ── Détection MIME image ────────────────────────────────────────────────────────

def test_sniff_image_mime():
    assert _sniff_image_mime(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert _sniff_image_mime(b"\xff\xd8\xff\xe0junk") == "image/jpeg"
    assert _sniff_image_mime(b"RIFF\x00\x00\x00\x00WEBPstuff") == "image/webp"
    assert _sniff_image_mime(b"not an image") is None


# ── XLSX (openpyxl) ─────────────────────────────────────────────────────────────

def test_extract_xlsx_one_segment_per_sheet(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "classeur.xlsx"
    wb = openpyxl.Workbook()
    ws0 = wb.active
    ws0.title = "Feuille1"
    ws0.append(["Nom", "Age"])
    ws0.append(["Alice", 30])
    ws1 = wb.create_sheet("Feuille2")
    ws1.append(["Produit"])
    ws1.append(["Vélo"])
    wb.save(path)

    result = _extract_xlsx(path)

    assert len(result.segments) == 2
    assert [s.page_idx for s in result.segments] == [0, 1]
    assert all(s.is_table for s in result.segments)
    assert "Alice" in result.segments[0].text
    assert "Vélo" in result.segments[1].text


# ── TXT ──────────────────────────────────────────────────────────────────────────

def test_extract_txt_splits_paragraphs(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("Premier paragraphe.\n\nDeuxième paragraphe.", encoding="utf-8")

    result = extract_document(path)

    assert [s.text for s in result.segments] == [
        "Premier paragraphe.",
        "Deuxième paragraphe.",
    ]
    assert all(s.page_idx == 0 for s in result.segments)


# ── PDF (PyMuPDF) : page_idx préservé ───────────────────────────────────────────

def test_extract_pdf_preserves_page_index(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "doc.pdf"
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Ceci est la toute premiere page du document.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Et voici un contenu distinct sur la seconde page.")
    doc.save(str(path))
    doc.close()

    result = extract_document(path)

    pages = {s.page_idx for s in result.segments}
    assert pages == {0, 1}
    # bbox conservée (bonus) : non nulle pour le texte PDF.
    assert all(s.bbox is not None for s in result.segments)


# ── extraction_to_content_blocks ─────────────────────────────────────────────────

def test_extraction_to_content_blocks_orders_and_reindexes():
    result = ExtractionResult(
        segments=[
            PageSegment(page_idx=0, text="Titre", is_title=True, title_level=1),
            PageSegment(page_idx=0, text="Texte page 0"),
            PageSegment(page_idx=1, text="Texte page 1"),
        ],
        images=[ExtractedImage(data=b"x", mime="image/png", page_idx=1)],
    )
    image_descriptions = [("Description image", 1)]

    blocks = extraction_to_content_blocks(result, image_descriptions)

    from openingestion.document import BlockKind

    # 3 segments + 1 image = 4 blocs, réindexés 0..3.
    assert [b.block_index for b in blocks] == [0, 1, 2, 3]
    assert [b.reading_order for b in blocks] == [0, 1, 2, 3]
    assert blocks[0].kind == BlockKind.TITLE
    assert blocks[0].title_level == 1
    # Tri par page : page 0 (titre, texte) puis page 1 (texte, image en dernier).
    assert [b.page_idx for b in blocks] == [0, 0, 1, 1]
    assert blocks[-1].kind == BlockKind.IMAGE


# ── Bout-en-bout : _ingest_simple sur un PDF multi-pages ─────────────────────────

def test_ingest_simple_pdf_end_to_end_page_aware(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    pytest.importorskip("openingestion")

    path = tmp_path / "rapport.pdf"
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Introduction. Le projet vise a ameliorer la recherche documentaire.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Conclusion. Les resultats obtenus sont encourageants pour la suite.")
    doc.save(str(path))
    doc.close()

    captured: dict = {}

    def fake_embed(chunk_dicts, *_args, **_kwargs):
        captured["chunk_dicts"] = chunk_dicts
        return ([[0.1] for _ in chunk_dicts], [[0.2] for _ in chunk_dicts])

    monkeypatch.setattr(ingestor, "_embed_content_and_titles", fake_embed)

    # chunk_size volontairement petit : force un chunk distinct par page
    # (sinon le contenu minuscule fusionne en un seul chunk multi-pages, dont
    # le page_idx serait celui de la première page — comportement légitime).
    chunk_dicts, content_vectors, title_vectors = ingestor._ingest_simple(
        document_path=path,
        source="rapport.pdf",
        api_key="api-key",
        embedding_model="text-embedding-3-small",
        chunk_size=20,
    )

    assert chunk_dicts, "des chunks doivent être produits"
    assert len(content_vectors) == len(chunk_dicts)
    assert len(title_vectors) == len(chunk_dicts)
    # Exigence produit : les chunks portent un page_idx, et les deux pages sont représentées.
    pages = {c["page_idx"] for c in chunk_dicts}
    assert pages == {0, 1}
    # Chaîne by_sentence : champs RagChunk présents dans les dicts.
    assert all("page_content" in c and "chunk_index" in c for c in chunk_dicts)
