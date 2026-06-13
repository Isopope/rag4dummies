"""Couche d'extraction de documents robuste, inspirée d'Onyx.

Réplique l'approche de ``onyx/file_processing/extract_file_text.py`` : un dispatch
par format qui retourne un résultat à plat, *page-aware*
(:class:`ExtractionResult`). Remplace la détection typographique fragile de
l'ancien ``_ingest_simple`` : ici on extrait du texte propre + des images, et la
structure (découpage par phrases) est déléguée en aval au ``SentenceChunker``
d'openingestion.

Différence clé avec Onyx : au lieu d'un unique ``text_content`` aplati, on
conserve des :class:`PageSegment` portant chacun leur ``page_idx``, afin que
l'UI puisse rouvrir le PDF à la bonne page (exigence produit). Les bboxes PDF
sont conservées en bonus quand elles sont gratuites (mode ``blocks`` de fitz).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

# Formats gérés par le mode fallback (cf. plan : inchangés).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt"}

# Ignore les images minuscules (icônes, puces, séparateurs décoratifs).
_MIN_IMAGE_BYTES = 3 * 1024  # 3 KB

# Signatures magic-bytes des formats raster courants (validation MIME façon Onyx).
_IMAGE_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
]


@dataclass
class PageSegment:
    """Fragment de texte rattaché à une page (ou section).

    page_idx    : index 0-based de page / slide / feuille. Propagé jusqu'au
                  RagChunk pour que l'UI ouvre le PDF à la bonne page.
    bbox        : ``[x0, y0, x1, y1]`` si disponible (PDF), sinon ``None``.
    is_title    : segment de titre (titre markdown ``#``/``##``) → bloc TITLE,
                  qui sert de frontière dure et alimente ``title_path``.
    title_level : niveau de titre (1-6) pour le breadcrumb.
    is_table    : contenu tabulaire conservé en un seul bloc TABLE.
    """

    page_idx: int
    text: str
    bbox: list[int] | None = None
    is_title: bool = False
    title_level: int = 0
    is_table: bool = False


@dataclass
class ExtractedImage:
    data: bytes
    mime: str
    page_idx: int


@dataclass
class ExtractionResult:
    segments: list[PageSegment] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _detect_encoding(data: bytes) -> str:
    """Détecte l'encodage via chardet, dégrade gracieusement sur utf-8."""
    try:
        import chardet

        guess = chardet.detect(data[:50_000])
        return guess.get("encoding") or "utf-8"
    except Exception:
        return "utf-8"


def _sniff_image_mime(data: bytes) -> str | None:
    """Retourne le type MIME d'une image via ses magic bytes, sinon None."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    for sig, mime in _IMAGE_MAGIC:
        if data.startswith(sig):
            return mime
    return None


def _split_paragraphs(text: str, page_idx: int) -> list[PageSegment]:
    """Découpe un texte en segments de paragraphe sur les lignes vides."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    segments: list[PageSegment] = []
    for para in text.split("\n\n"):
        stripped = para.strip()
        if stripped:
            segments.append(PageSegment(page_idx=page_idx, text=stripped))
    return segments


# ── PDF (PyMuPDF / fitz) ──────────────────────────────────────────────────────

def _extract_pdf_image(doc, xref: int, page_idx: int) -> ExtractedImage | None:
    """Extrait une image PDF en PNG. Libère correctement le Pixmap (pas de fuite)."""
    import fitz

    pix = None
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha > 3:  # CMYK / espace non-RGB → conversion
            converted = fitz.Pixmap(fitz.csRGB, pix)
            pix.delete()  # libère l'original avant réassignation (correctif fuite)
            pix = converted
        return ExtractedImage(data=pix.tobytes("png"), mime="image/png", page_idx=page_idx)
    except Exception as exc:  # image corrompue / format exotique → on saute
        logger.warning("Extraction image PDF (xref={}) échouée : {}", xref, exc)
        return None
    finally:
        if pix is not None:
            try:
                pix.delete()
            except Exception:
                pass


def _extract_pdf(path: Path) -> ExtractionResult:
    import fitz

    result = ExtractionResult()
    doc = fitz.open(str(path))
    try:
        meta = doc.metadata or {}
        title = (meta.get("title") or "").strip()
        result.metadata["title"] = title or path.stem

        for page in doc:
            page_idx = page.number
            # Texte à plat par bloc fitz, sans heuristique de titre. bbox conservée.
            for block in page.get_text("blocks"):
                # block = (x0, y0, x1, y1, text, block_no, block_type)
                if len(block) >= 7 and block[6] != 0:
                    continue  # ignore les blocs non-texte (images)
                text = (block[4] or "").strip()
                if not text:
                    continue
                bbox = [int(block[0]), int(block[1]), int(block[2]), int(block[3])]
                result.segments.append(
                    PageSegment(page_idx=page_idx, text=text, bbox=bbox)
                )

            for img_info in page.get_images(full=True):
                img = _extract_pdf_image(doc, img_info[0], page_idx)
                if img is not None and len(img.data) >= _MIN_IMAGE_BYTES:
                    result.images.append(img)
    finally:
        doc.close()
    return result


# ── Office (markitdown → markdown) ─────────────────────────────────────────────

def _markdown_to_segments(markdown: str) -> list[PageSegment]:
    """Convertit du markdown en segments page 0.

    - Titres ``#``/``##`` → segments TITLE (fiable, alimente title_path).
    - Lignes de tableau ``| … |`` consécutives regroupées en UN bloc TABLE
      (fin de l'explosion par ligne) ; lignes de séparation ``|---|`` ignorées.
    - Paragraphes accumulés jusqu'à une ligne vide.
    """
    segments: list[PageSegment] = []
    table_lines: list[str] = []
    paragraph_lines: list[str] = []

    def flush_table() -> None:
        if table_lines:
            segments.append(
                PageSegment(page_idx=0, text="\n".join(table_lines), is_table=True)
            )
            table_lines.clear()

    def flush_paragraph() -> None:
        if paragraph_lines:
            text = " ".join(line.strip() for line in paragraph_lines).strip()
            if text:
                segments.append(PageSegment(page_idx=0, text=text))
            paragraph_lines.clear()

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            if set(stripped) <= set("|-: "):  # ligne de séparation markdown
                continue
            table_lines.append(stripped)
            continue
        flush_table()

        if not stripped:
            flush_paragraph()
            continue

        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            if text:
                segments.append(
                    PageSegment(
                        page_idx=0, text=text, is_title=True, title_level=min(level, 6)
                    )
                )
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_table()
    return segments


def _extract_zip_images(path: Path, media_prefix: str) -> list[ExtractedImage]:
    """Extrait les images d'un conteneur Office (zip), filtrées par taille + MIME."""
    import zipfile

    images: list[ExtractedImage] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.startswith(media_prefix) or name.endswith("/"):
                    continue
                data = archive.read(name)
                if len(data) < _MIN_IMAGE_BYTES:
                    continue
                mime = _sniff_image_mime(data)
                if mime is None:
                    continue
                images.append(ExtractedImage(data=data, mime=mime, page_idx=0))
    except Exception as exc:
        logger.warning("Extraction images zip échouée sur {} : {}", path.name, exc)
    return images


def _extract_office_markdown(path: Path, media_prefix: str) -> ExtractionResult:
    """DOCX / PPTX → markdown via markitdown, avec fallback texte sur zip invalide."""
    from markitdown import MarkItDown

    result = ExtractionResult()
    result.metadata["title"] = path.stem

    md = MarkItDown(enable_plugins=False)
    try:
        converted = md.convert(str(path))
        markdown = (
            getattr(converted, "markdown", None)
            or getattr(converted, "text_content", "")
            or ""
        )
    except Exception as exc:
        # docx/pptx invalide mais peut-être un fichier texte → fallback Onyx-style.
        logger.warning(
            "markitdown a échoué sur {} : {}. Tentative en texte brut.", path.name, exc
        )
        return _extract_txt(path)

    result.segments = _markdown_to_segments(markdown)
    result.images = _extract_zip_images(path, media_prefix)
    return result


# ── XLSX (openpyxl, façon Onyx) ────────────────────────────────────────────────

def _extract_xlsx(path: Path) -> ExtractionResult:
    import openpyxl

    result = ExtractionResult()
    result.metadata["title"] = path.stem

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        logger.warning("openpyxl a échoué sur {} : {}", path.name, exc)
        return result

    try:
        for sheet_idx, sheet in enumerate(workbook.worksheets):
            rows: list[str] = []
            empty_streak = 0
            for row in sheet.iter_rows(values_only=True):
                row_str = ",".join("" if cell is None else str(cell) for cell in row)
                if row_str.strip(","):
                    rows.append(row_str)
                    empty_streak = 0
                else:
                    empty_streak += 1
                    if empty_streak > 100:  # feuilles massives à cellules vides
                        logger.warning(
                            "Trop de lignes vides dans {} (feuille {}), arrêt.",
                            path.name,
                            sheet.title,
                        )
                        break
            if rows:
                text = f"{sheet.title}\n" + "\n".join(rows)
                result.segments.append(
                    PageSegment(page_idx=sheet_idx, text=text, is_table=True)
                )
    finally:
        workbook.close()
    return result


# ── TXT ────────────────────────────────────────────────────────────────────────

def _extract_txt(path: Path) -> ExtractionResult:
    result = ExtractionResult()
    result.metadata["title"] = path.stem
    data = path.read_bytes()
    # utf-8 d'abord (cas courant ; chardet devine mal sur les échantillons courts),
    # chardet en repli pour les fichiers réellement non-utf-8.
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode(_detect_encoding(data), errors="replace")
    result.segments = _split_paragraphs(text, page_idx=0)
    return result


# ── Dispatch ─────────────────────────────────────────────────────────────────

def extract_document(path: Path) -> ExtractionResult:
    """Extrait le contenu d'un document selon son extension (dispatch façon Onyx)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_office_markdown(path, "word/media/")
    if ext == ".pptx":
        return _extract_office_markdown(path, "ppt/media/")
    if ext == ".xlsx":
        return _extract_xlsx(path)
    if ext == ".txt":
        return _extract_txt(path)
    raise RuntimeError(
        f"Format non supporté en mode fallback : {ext or 'sans extension'}"
    )
