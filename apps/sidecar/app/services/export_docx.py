"""Renders a ``CompiledDocument`` (built by ``export_service.build_compiled_document``,
docs/06 Phase 6 task BE-2) to a Microsoft Word ``.docx`` file, per task BE-4.

PURE TRANSFORM — this module does ZERO database access. It never queries the ORM, never
resolves an ``Image`` row, and never writes to disk itself; it only ever takes an already-
materialized ``CompiledDocument`` (+ optionally an already-resolved cover image file path)
and returns ``.docx`` bytes. The caller (BE-7's export router) is responsible for resolving
``CompiledDocument.cover_image_id`` to a safe on-disk path (e.g. via
``images_service.resolve_path``'s escape guard) *before* calling :func:`render_docx` — this
module trusts ``cover_image_path`` is already safe, but still defensively wraps the actual
image read in a try/except (see below) so a missing/corrupt file degrades to "skip the
image" rather than aborting an otherwise-valid export.

Security note (this file gets a mandatory reviewer pass per CLAUDE.md's hard rule on
``export_docx.py``): every piece of user-supplied text — chapter/scene titles, scene
descriptions, screenplay element text, and ``front_matter`` values — is written into the
``.docx`` exclusively via python-docx's own ``paragraph.add_run(text)`` / ``add_heading``
APIs. There is no raw XML string concatenation anywhere in this module; python-docx owns
all XML escaping. There is also no ``eval``/template-string execution of any user content.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from app.services.export_service import CompiledChapter, CompiledDocument

logger = logging.getLogger(__name__)

_SCRIPT_BOOK_TYPES = {"movie_script", "short_film_script"}

# Approximate industry-adjacent indentation per screenplay element type — this working-draft
# .docx export doesn't need to be pixel-perfect (that's the Fountain/FDX path's job).
_SCRIPT_ELEMENT_INDENT_INCHES: dict[str, float] = {
    "scene_heading": 0.0,
    "action": 0.0,
    "character": 2.0,
    "dialogue": 1.0,
    "parenthetical": 1.5,
    "transition": 0.0,
}

_COVER_IMAGE_WIDTH_INCHES = 4.0


def render_docx(doc: CompiledDocument, cover_image_path: Path | None = None) -> bytes:
    """Renders ``doc`` to ``.docx`` bytes.

    ``cover_image_path``, if given, MUST already have been validated safe by the caller
    (e.g. resolved via ``images_service.resolve_path``, which raises on path escape) — this
    function does no such validation itself, only a defensive try/except around the actual
    embed so a missing/corrupt file never crashes an otherwise-valid export.
    """
    docx_document = Document()

    _render_title_page(docx_document, doc, cover_image_path)

    if doc.book_type in _SCRIPT_BOOK_TYPES:
        _apply_script_formatting(docx_document)
        _render_script_body(docx_document, doc)
    else:
        _render_prose_body(docx_document, doc)

    buffer = io.BytesIO()
    docx_document.save(buffer)
    return buffer.getvalue()


# ── Title page ───────────────────────────────────────────────────────────────────


def _render_title_page(
    docx_document: Document, doc: CompiledDocument, cover_image_path: Path | None
) -> None:
    title_paragraph = docx_document.add_paragraph()
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_paragraph.add_run(doc.book_title)
    title_run.bold = True
    title_run.font.size = Pt(28)

    if doc.logline:
        logline_paragraph = docx_document.add_paragraph()
        logline_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        logline_run = logline_paragraph.add_run(doc.logline)
        logline_run.italic = True

    if doc.front_matter:
        for key, value in doc.front_matter.items():
            # Non-string values (a list/dict a user somehow stashed in front_matter) are
            # coerced rather than crashing the export.
            text = value if isinstance(value, str) else str(value)
            if not text:
                continue
            fm_paragraph = docx_document.add_paragraph()
            fm_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if key == "subtitle":
                fm_run = fm_paragraph.add_run(text)
                fm_run.italic = True
            else:
                label = key.replace("_", " ").title()
                fm_paragraph.add_run(f"{label}: {text}")

    if cover_image_path is not None:
        try:
            if cover_image_path.exists():
                docx_document.add_picture(
                    str(cover_image_path), width=Inches(_COVER_IMAGE_WIDTH_INCHES)
                )
                docx_document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:
            # A bad/corrupt/mismatched image file must never abort an otherwise-valid
            # export — skip the image and keep going.
            logger.warning(
                "export_docx: failed to embed cover image at %s; skipping image",
                cover_image_path,
                exc_info=True,
            )

    docx_document.add_page_break()


# ── Prose body ───────────────────────────────────────────────────────────────────


def _render_prose_body(docx_document: Document, doc: CompiledDocument) -> None:
    for chapter_index, chapter in enumerate(doc.chapters):
        if chapter_index > 0:
            docx_document.add_page_break()
        _render_chapter_heading(docx_document, chapter)
        for scene in chapter.scenes:
            scene_heading = docx_document.add_heading(level=3)
            scene_heading.add_run(scene.title)
            for paragraph_text in _split_into_paragraphs(scene.description):
                body_paragraph = docx_document.add_paragraph(style="Normal")
                body_paragraph.add_run(paragraph_text)


# ── Script body ──────────────────────────────────────────────────────────────────


def _apply_script_formatting(docx_document: Document) -> None:
    """Courier New 12pt for the whole body + industry-adjacent margins. Applied AFTER the
    title page is rendered so the title page keeps its own (non-Courier) styling."""
    section = docx_document.sections[0]
    section.left_margin = Inches(1.5)
    section.right_margin = Inches(1.0)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)

    normal_style = docx_document.styles["Normal"]
    normal_style.font.name = "Courier New"
    normal_style.font.size = Pt(12)


def _render_script_body(docx_document: Document, doc: CompiledDocument) -> None:
    for chapter_index, chapter in enumerate(doc.chapters):
        if chapter_index > 0:
            docx_document.add_page_break()
        _render_chapter_heading(docx_document, chapter)
        for scene in chapter.scenes:
            if scene.elements:
                for element in sorted(scene.elements, key=lambda e: e.order_index):
                    element_paragraph = docx_document.add_paragraph(style="Normal")
                    indent_inches = _SCRIPT_ELEMENT_INDENT_INCHES.get(element.element_type, 0.0)
                    element_paragraph.paragraph_format.left_indent = Inches(indent_inches)
                    element_paragraph.add_run(element.text)
            elif scene.description:
                for paragraph_text in _split_into_paragraphs(scene.description):
                    body_paragraph = docx_document.add_paragraph(style="Normal")
                    body_paragraph.add_run(paragraph_text)


# ── Shared helpers ───────────────────────────────────────────────────────────────


def _render_chapter_heading(docx_document: Document, chapter: CompiledChapter) -> None:
    """No heading at all if ``chapter.title is None`` (the chapterless bucket) — just its
    scenes' content, per task BE-4's instructions."""
    if chapter.title is None:
        return
    heading = docx_document.add_heading(level=1)
    heading.add_run(chapter.title)


def _split_into_paragraphs(text: str) -> list[str]:
    """Splits prose text on blank lines (``\\n\\n``) into separate paragraph strings, so a
    long block of prose doesn't render as one unreadable paragraph. Empty/whitespace-only
    chunks are dropped; an empty/``None``-ish ``text`` yields no paragraphs at all."""
    if not text:
        return []
    return [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
