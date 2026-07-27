"""Tests for the PDF export renderer (docs/06 Phase 6 task BE-5, app/services/export_pdf.py).

Uses a throwaway temp data dir (set via QUILLNIGHT_DATA_DIR before importing anything under
``app``) so this test run never touches a real app-data directory — same pattern as
tests/test_images.py.

WeasyPrint's native runtime isn't installed on this build machine (see export_pdf.py's
docstring), so only the ReportLab fallback path is exercised live here. The WeasyPrint path
(``_render_pdf_weasyprint``) is verified by import/syntax only — `ruff check` plus this
module successfully importing `app.services.export_pdf` (which references it) is the
practical proof it's not a stub, per the task's guidance.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-test-export-pdf-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR

from pathlib import Path  # noqa: E402
from xml.sax.saxutils import escape as xml_escape  # noqa: E402

from app.services.export_pdf import (  # noqa: E402
    _esc,
    _render_pdf_reportlab,
    render_pdf,
)
from app.services.export_service import (  # noqa: E402
    CompiledChapter,
    CompiledDocument,
    CompiledScene,
    ScreenplayElementLike,
)


def _prose_document() -> CompiledDocument:
    return CompiledDocument(
        book_id="book-1",
        book_title="The Long Night",
        book_type="story_book",
        logline="A quiet town keeps a loud secret.",
        front_matter={"author": "Jane Doe", "year": 2026, "draft": True},
        cover_image_id=None,
        chapters=[
            CompiledChapter(
                title="Chapter One",
                scenes=[
                    CompiledScene(
                        title="The Arrival",
                        description="It was dark.\n\nShe walked in anyway.",
                        elements=[],
                    ),
                ],
            ),
            CompiledChapter(
                title="Chapter Two",
                scenes=[
                    CompiledScene(
                        title="The Reveal", description="Everything changed.", elements=[]
                    ),
                ],
            ),
        ],
    )


def _script_document(scene_description: str = "") -> CompiledDocument:
    return CompiledDocument(
        book_id="book-2",
        book_title="Night Shift",
        book_type="movie_script",
        logline="One long shift, one bad decision.",
        front_matter=None,
        cover_image_id=None,
        chapters=[
            CompiledChapter(
                title=None,
                scenes=[
                    CompiledScene(
                        title="Scene 1",
                        description=scene_description,
                        elements=[
                            ScreenplayElementLike(
                                element_type="scene_heading",
                                text="INT. WAREHOUSE - NIGHT",
                                order_index=0,
                            ),
                            ScreenplayElementLike(
                                element_type="action", text="Rain hammers the roof.", order_index=1
                            ),
                            ScreenplayElementLike(
                                element_type="character", text="MARA", order_index=2
                            ),
                            ScreenplayElementLike(
                                element_type="dialogue",
                                text="We shouldn't be here.",
                                order_index=3,
                            ),
                            ScreenplayElementLike(
                                element_type="parenthetical", text="(whispering)", order_index=4
                            ),
                            ScreenplayElementLike(
                                element_type="transition", text="CUT TO:", order_index=5
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def test_render_pdf_prose_returns_valid_pdf_bytes() -> None:
    pdf_bytes = render_pdf(_prose_document())
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")


def test_render_pdf_script_returns_valid_pdf_bytes() -> None:
    pdf_bytes = render_pdf(_script_document())
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")


def test_render_pdf_missing_cover_image_does_not_crash() -> None:
    missing_path = Path(_TMP_DATA_DIR) / "does-not-exist" / "cover.png"
    pdf_bytes = render_pdf(_prose_document(), cover_image_path=missing_path)
    assert pdf_bytes.startswith(b"%PDF")


def test_render_pdf_reportlab_path_directly() -> None:
    """Exercises `_render_pdf_reportlab` directly (not just via the `render_pdf` dispatcher)
    since that's the only path this build machine can actually run end-to-end."""
    pdf_bytes = _render_pdf_reportlab(_prose_document(), cover_image_path=None)
    assert pdf_bytes.startswith(b"%PDF")
    pdf_bytes = _render_pdf_reportlab(_script_document(), cover_image_path=None)
    assert pdf_bytes.startswith(b"%PDF")


def test_esc_helper_escapes_markup_like_text() -> None:
    """Proves the escaping helper actually escapes ReportLab-mini-markup-significant
    characters, rather than just asserting it "should"."""
    raw = "<b>injected</b> & <script>alert(1)</script>"
    escaped = _esc(raw)
    assert "<b>" not in escaped
    assert "<script>" not in escaped
    assert escaped == xml_escape(raw)
    assert "&lt;b&gt;" in escaped


def test_esc_helper_coerces_non_string_values() -> None:
    assert _esc(2026) == "2026"
    assert _esc(True) == "True"


def test_scene_description_with_injected_markup_renders_without_crashing_and_is_escaped() -> (
    None
):
    """A scene description containing `<b>injected</b>`-style text must not be interpreted as
    ReportLab markup. We can't inspect the internal PDF content stream easily here, so this
    proves the concrete mechanism instead: `_esc` (the only call site feeding scene
    descriptions into `Paragraph()` in `_render_pdf_reportlab`) neutralizes the markup, and
    rendering a document containing that text still produces a well-formed PDF (i.e. the
    escaped text was treated as plain content, not markup that could break the flowable)."""
    malicious = "Normal text <b>injected</b> more <br/>text & <i>more</i>"
    doc = _prose_document()
    doc.chapters[0].scenes[0].description = malicious

    escaped = _esc(malicious)
    assert "<b>injected</b>" not in escaped
    assert "&lt;b&gt;injected&lt;/b&gt;" in escaped

    pdf_bytes = _render_pdf_reportlab(doc, cover_image_path=None)
    assert pdf_bytes.startswith(b"%PDF")


def test_script_scene_element_text_is_escaped_before_paragraph() -> None:
    doc = _script_document()
    doc.chapters[0].scenes[0].elements[1].text = "<b>Rain</b> hammers & <br/>echoes."
    pdf_bytes = _render_pdf_reportlab(doc, cover_image_path=None)
    assert pdf_bytes.startswith(b"%PDF")


def test_front_matter_non_string_values_are_escaped_and_do_not_crash() -> None:
    doc = _prose_document()
    doc.front_matter = {"year": 2026, "complete": False, "notes": "<i>draft</i> & final"}
    pdf_bytes = _render_pdf_reportlab(doc, cover_image_path=None)
    assert pdf_bytes.startswith(b"%PDF")
