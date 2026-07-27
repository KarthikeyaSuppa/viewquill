"""PDF renderer for the Final Draft export pipeline (docs/06 Phase 6 task BE-5).

Consumes ``export_service.CompiledDocument`` — the same fully-materialized, format-agnostic
shape ``export_docx.py``/``export_service`` build — and returns raw PDF ``bytes``. Like every
other renderer in this pipeline, this module is a pure transform: it never writes to disk
itself, that's the caller's (router's) job.

DUAL-PATH, ONE PUBLIC ENTRY POINT: :func:`render_pdf` tries WeasyPrint first (HTML/CSS via
Jinja2, ``app/templates/draft.html.j2`` + ``draft-manuscript.css``/``draft-screenplay.css``)
and falls back to a pure-Python ReportLab Platypus builder if WeasyPrint's native runtime
isn't available. On THIS build machine ``import weasyprint`` raises ``OSError`` (missing
GTK/Pango/cairo — see ``pyproject.toml``'s comment and ``app/services/images_service.py``'s
precedent for documenting a native-dependency gap inline), so the ReportLab path is the one
actually exercised here; the WeasyPrint path is fully written and syntactically valid so it
activates automatically the moment the native runtime is present (e.g. on the target ASUS
laptop) — nothing else needs to change.

SECURITY (this file is flagged for a mandatory `reviewer` pass per CLAUDE.md — encroaches on
generated-document code): every piece of user-controlled text that reaches ReportLab's
``Paragraph()`` constructor is escaped first via :func:`_esc` (``xml.sax.saxutils.escape``) —
ReportLab's Platypus ``Paragraph`` interprets a small XML-like markup language internally
(``<b>``, ``<br/>``, etc.), so un-escaped user text could corrupt styling or be misread as a
tag. The WeasyPrint/Jinja2 HTML path relies on Jinja2's autoescaping instead (turned on
explicitly via ``Environment(..., autoescape=True)`` in ``_render_pdf_weasyprint`` below —
never disabled, never bypassed with a ``| safe`` filter in ``draft.html.j2``). Neither path
ever string-concatenates user text directly into HTML or ReportLab markup.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from app.services.export_service import CompiledDocument

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Screenplay indentation, expressed in inches from the page's left margin — deliberately
# approximate industry-standard values; this is a PDF *export*, not a Fountain/FDX authoring
# format, so exact conformance isn't the goal (mirrors draft-screenplay.css's .el-* rules).
_SCRIPT_LEFT_INDENT_IN: dict[str, float] = {
    "scene_heading": 0.0,
    "action": 0.0,
    "shot": 0.0,
    "character": 2.2,
    "dialogue": 1.0,
    "dual_dialogue": 1.0,
    "parenthetical": 1.6,
    "transition": 0.0,
}


def _esc(value: object) -> str:
    """Coerces ``value`` to ``str`` (front_matter values may be numbers/bools/etc.) and
    HTML/XML-escapes it via ``xml.sax.saxutils.escape``. This is the ONE call site every
    piece of user-controlled text (book title, logline, front_matter values, chapter/scene
    titles, scene descriptions, screenplay element text) must pass through before reaching
    ReportLab's ``Paragraph()`` constructor — see this module's docstring."""
    return _xml_escape(str(value))


def _is_script_document(doc: CompiledDocument) -> bool:
    """A document is treated as a screenplay for rendering purposes if ANY compiled scene
    carries screenplay elements — mirrors ``export_service.build_compiled_document``'s own
    rule (elements are only ever attached for ``movie_script``/``short_film_script`` book
    types), without this module needing to depend on that module's private book-type set."""
    return any(scene.elements for chapter in doc.chapters for scene in chapter.scenes)


def render_pdf(doc: CompiledDocument, cover_image_path: Path | None = None) -> bytes:
    """The one public entry point the export router calls. Tries WeasyPrint (HTML/CSS via
    Jinja2) first; falls back to ReportLab (pure Python) if WeasyPrint's native runtime isn't
    importable on this machine. Always returns PDF ``bytes`` — never writes to disk."""
    try:
        import weasyprint  # noqa: F401  (import-success is the only thing we need here)
    except (ImportError, OSError):
        # OSError is the ACTUAL failure mode observed on this build machine — native
        # GTK/Pango/cairo libraries missing surface as OSError at import time, not
        # ImportError. See this module's docstring.
        logger.info("WeasyPrint unavailable; rendering PDF via ReportLab fallback.")
        return _render_pdf_reportlab(doc, cover_image_path)
    return _render_pdf_weasyprint(doc, cover_image_path)


# ── WeasyPrint path (HTML/CSS via Jinja2) ────────────────────────────────────────


def _render_pdf_weasyprint(doc: CompiledDocument, cover_image_path: Path | None) -> bytes:
    """Renders ``doc`` to PDF bytes via WeasyPrint: builds an HTML string from
    ``app/templates/draft.html.j2`` (Jinja2, autoescape ON) with one of
    ``draft-manuscript.css``/``draft-screenplay.css`` (chosen by whether ``doc`` carries any
    screenplay elements) inlined into the page, then ``weasyprint.HTML(...).write_pdf()``.

    Not exercised live on this build machine (no WeasyPrint native runtime — see this
    module's docstring); kept fully written and syntactically valid so it activates
    automatically once the runtime is available elsewhere."""
    import weasyprint
    from jinja2 import Environment, FileSystemLoader

    is_script = _is_script_document(doc)
    css_filename = "draft-screenplay.css" if is_script else "draft-manuscript.css"
    css = (TEMPLATES_DIR / css_filename).read_text(encoding="utf-8")

    cover_image_uri: str | None = None
    if cover_image_path is not None:
        try:
            if cover_image_path.is_file():
                cover_image_uri = cover_image_path.resolve().as_uri()
        except OSError:
            # Missing/unreadable cover image is never fatal — same
            # try/skip-don't-crash contract as the ReportLab path below.
            cover_image_uri = None

    # autoescape=True (never disabled, never bypassed with `| safe` in the template) is the
    # entire XSS/injection defense for this path — see this module's docstring.
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("draft.html.j2")
    html_string = template.render(
        doc=doc, css=css, is_script=is_script, cover_image_uri=cover_image_uri
    )

    pdf_bytes: bytes = weasyprint.HTML(string=html_string, base_url=str(TEMPLATES_DIR)).write_pdf()
    return pdf_bytes


# ── ReportLab path (pure Python, no native runtime needed) ──────────────────────


def _reportlab_styles(is_script: bool) -> dict[str, ParagraphStyle]:
    """Builds the named ``ParagraphStyle``s used by :func:`_render_pdf_reportlab`. Script
    books use ``fontName="Courier"`` throughout; prose books use the ReportLab default
    (Helvetica-family) sample stylesheet as a base."""
    base = getSampleStyleSheet()
    font = "Courier" if is_script else "Helvetica"
    bold_font = "Courier-Bold" if is_script else "Helvetica-Bold"

    styles: dict[str, ParagraphStyle] = {
        "title": ParagraphStyle(
            "QNTitle",
            parent=base["Title"],
            fontName=bold_font,
            fontSize=26,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "logline": ParagraphStyle(
            "QNLogline",
            parent=base["Italic"],
            fontName=font,
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "front_matter": ParagraphStyle(
            "QNFrontMatter",
            parent=base["Normal"],
            fontName=font,
            fontSize=10,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "chapter_title": ParagraphStyle(
            "QNChapterTitle",
            parent=base["Heading1"],
            fontName=bold_font,
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=16,
        ),
        "scene_title": ParagraphStyle(
            "QNSceneTitle",
            parent=base["Heading2"],
            fontName=bold_font,
            fontSize=13,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "QNBody",
            parent=base["Normal"],
            fontName=font,
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
    }

    oblique_font = "Courier-Oblique" if is_script else "Helvetica-Oblique"

    for element_type, indent_in in _SCRIPT_LEFT_INDENT_IN.items():
        alignment = TA_RIGHT if element_type == "transition" else TA_LEFT
        upper_bold = element_type in ("scene_heading", "character")
        if element_type == "parenthetical":
            element_font = oblique_font
        elif upper_bold:
            element_font = bold_font
        else:
            element_font = font
        styles[f"el_{element_type}"] = ParagraphStyle(
            f"QNEl_{element_type}",
            parent=base["Normal"],
            fontName=element_font,
            fontSize=11,
            leading=14,
            alignment=alignment,
            leftIndent=indent_in * inch,
            spaceAfter=6,
        )
    return styles


def _render_pdf_reportlab(doc: CompiledDocument, cover_image_path: Path | None) -> bytes:
    """Renders ``doc`` to PDF bytes via ReportLab's Platypus flowables, consuming
    ``CompiledDocument`` directly (no HTML/Jinja2 step — ReportLab isn't an HTML renderer).

    Every piece of user-controlled text is passed through :func:`_esc` before being wrapped
    in a ``Paragraph(...)`` call — see this module's docstring."""
    is_script = _is_script_document(doc)
    styles = _reportlab_styles(is_script)
    flowables: list = []

    # ── Title page ────────────────────────────────────────────────
    flowables.append(Paragraph(_esc(doc.book_title), styles["title"]))
    if doc.logline:
        flowables.append(Paragraph(_esc(doc.logline), styles["logline"]))
    flowables.append(Spacer(1, 12))

    if doc.front_matter:
        for key, value in doc.front_matter.items():
            flowables.append(
                Paragraph(f"<b>{_esc(key)}:</b> {_esc(value)}", styles["front_matter"])
            )
        flowables.append(Spacer(1, 12))

    if cover_image_path is not None:
        try:
            if cover_image_path.is_file():
                flowables.append(Spacer(1, 12))
                flowables.append(
                    RLImage(str(cover_image_path), width=3.5 * inch, height=5 * inch)
                )
        except Exception:
            # Missing/corrupt cover image is never fatal to the export — same
            # try/except-skip contract as export_docx.py.
            logger.warning("Skipping cover image for PDF export.", exc_info=True)

    flowables.append(PageBreak())

    # ── Chapters/scenes ───────────────────────────────────────────
    for chapter_index, chapter in enumerate(doc.chapters):
        if chapter.title:
            flowables.append(Paragraph(_esc(chapter.title), styles["chapter_title"]))

        for scene in chapter.scenes:
            flowables.append(Paragraph(_esc(scene.title), styles["scene_title"]))

            for para_text in (scene.description or "").split("\n\n"):
                if para_text.strip():
                    flowables.append(Paragraph(_esc(para_text), styles["body"]))

            if is_script:
                for element in scene.elements:
                    style = styles.get(f"el_{element.element_type}", styles["body"])
                    flowables.append(Paragraph(_esc(element.text), style))

        if chapter_index < len(doc.chapters) - 1:
            flowables.append(PageBreak())

    buffer = io.BytesIO()
    pdf_doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
    )
    pdf_doc.build(flowables)
    return buffer.getvalue()
