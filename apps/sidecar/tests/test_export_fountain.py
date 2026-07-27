"""Tests for Fountain/FDX rendering (docs/06 Phase 6 task BE-6).

Pure unit tests against ``export_fountain``'s two render functions and the plain
``CompiledDocument`` dataclasses from ``export_service`` — no DB/app needed, since
``build_compiled_document`` (the DB-touching half) is out of scope for this task.

Every ``ET.fromstring`` call below parses XML this test itself just generated via
``render_fdx`` (never third-party/network input), so the ``S314`` "untrusted XML"
lint warning doesn't apply here and is silenced per-call.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.services.export_fountain import _sanitize, render_fdx, render_fountain
from app.services.export_service import (
    CompiledChapter,
    CompiledDocument,
    CompiledScene,
    ScreenplayElementLike,
)


def _script_doc(
    scene_elements: list[ScreenplayElementLike], scene_description: str = ""
) -> CompiledDocument:
    scene = CompiledScene(
        title="Scene One",
        description=scene_description,
        elements=scene_elements,
    )
    chapter = CompiledChapter(title="Act One", scenes=[scene])
    return CompiledDocument(
        book_id="book-1",
        book_title="Test Script",
        book_type="movie_script",
        logline="A logline.",
        front_matter=None,
        cover_image_id=None,
        chapters=[chapter],
    )


def _basic_elements() -> list[ScreenplayElementLike]:
    return [
        ScreenplayElementLike(
            element_type="scene_heading", text="INT. HOUSE - DAY", order_index=0
        ),
        ScreenplayElementLike(
            element_type="action", text="John enters the room.", order_index=1
        ),
        ScreenplayElementLike(element_type="character", text="JOHN", order_index=2),
        ScreenplayElementLike(element_type="dialogue", text="Hello, world.", order_index=3),
    ]


def test_render_fountain_nonempty_with_scene_heading_marker():
    doc = _script_doc(_basic_elements())
    fountain_text = render_fountain(doc)

    assert isinstance(fountain_text, str)
    assert fountain_text.strip() != ""
    assert "INT. HOUSE - DAY" in fountain_text
    assert "JOHN" in fountain_text
    assert "Hello, world." in fountain_text


def test_render_fdx_nonempty_and_well_formed_xml():
    doc = _script_doc(_basic_elements())
    fdx_text = render_fdx(doc)

    assert isinstance(fdx_text, str)
    assert fdx_text.strip() != ""

    root = ET.fromstring(fdx_text)  # noqa: S314 — parses our own just-rendered output
    assert root.tag == "FinalDraft"

    texts = [t.text for t in root.iter("Text")]
    assert "INT. HOUSE - DAY" in texts
    assert "John enters the room." in texts
    assert "JOHN" in texts
    assert "Hello, world." in texts


def test_render_fdx_escapes_special_characters_round_trip():
    dangerous_text = 'Rock & Roll <loud> "quoted" \'single\''
    elements = [
        ScreenplayElementLike(
            element_type="scene_heading", text="INT. STUDIO - NIGHT", order_index=0
        ),
        ScreenplayElementLike(element_type="action", text=dangerous_text, order_index=1),
    ]
    doc = _script_doc(elements)
    fdx_text = render_fdx(doc)

    # Not literally present as raw XML — proves it was escaped, not injected.
    assert "<loud>" not in fdx_text
    assert "&amp;" in fdx_text or "&#38;" in fdx_text

    root = ET.fromstring(fdx_text)  # noqa: S314 — parses our own just-rendered output
    texts = [t.text for t in root.iter("Text")]
    assert dangerous_text in texts


def test_scene_description_preserved_as_action_and_not_lost():
    doc = _script_doc(_basic_elements(), scene_description="Prose notes about this scene.")
    fdx_text = render_fdx(doc)
    root = ET.fromstring(fdx_text)  # noqa: S314 — parses our own just-rendered output
    texts = [t.text for t in root.iter("Text")]
    assert "Prose notes about this scene." in texts

    fountain_text = render_fountain(doc)
    assert "Prose notes about this scene." in fountain_text


def test_scene_without_leading_scene_heading_synthesizes_one_from_title():
    elements = [
        ScreenplayElementLike(element_type="action", text="No heading present.", order_index=0),
    ]
    doc = _script_doc(elements)
    doc.chapters[0].scenes[0].title = "Synthesized Heading Scene"

    fdx_text = render_fdx(doc)
    root = ET.fromstring(fdx_text)  # noqa: S314 — parses our own just-rendered output
    headings = [
        p.find("Text").text for p in root.iter("Paragraph") if p.get("Type") == "Scene Heading"
    ]
    assert "Synthesized Heading Scene" in headings


def test_chapter_title_preserved_in_both_formats():
    doc = _script_doc(_basic_elements())

    fountain_text = render_fountain(doc)
    assert "Act One" in fountain_text

    fdx_text = render_fdx(doc)
    root = ET.fromstring(fdx_text)  # noqa: S314 — parses our own just-rendered output
    texts = [t.text for t in root.iter("Text")]
    assert "Act One" in texts


@pytest.mark.parametrize("fmt_fn", [render_fountain, render_fdx])
def test_non_script_book_type_rejected(fmt_fn):
    doc = _script_doc(_basic_elements())
    doc.book_type = "story_book"
    with pytest.raises(ValueError, match="FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE"):
        fmt_fn(doc)


def test_render_fdx_strips_xml_invalid_control_chars_instead_of_crashing():
    """``\\x01``/``\\x0b`` are XML-illegal (XML 1.0 §2.2) and previously reached
    ``xml.dom.minidom.parseString`` unescaped, raising ``ExpatError: not well-formed (invalid
    token)`` and crashing the whole export for one stray byte (e.g. from dictation/STT or a
    corrupted paste). They must now be stripped, and the resulting FDX must still be valid XML."""
    elements = [
        ScreenplayElementLike(
            element_type="scene_heading", text="INT. HOUSE - DAY", order_index=0
        ),
        ScreenplayElementLike(
            element_type="action", text="bad\x01byte\x0bhere", order_index=1
        ),
    ]
    doc = _script_doc(elements)

    fdx_text = render_fdx(doc)  # must not raise xml.parsers.expat.ExpatError

    root = ET.fromstring(fdx_text)  # noqa: S314 — parses our own just-rendered output
    texts = [t.text for t in root.iter("Text")]
    assert "badbytehere" in texts
    assert not any("\x01" in (t or "") or "\x0b" in (t or "") for t in texts)


def test_render_fountain_strips_xml_invalid_control_chars_for_consistency():
    """Fountain is plain text and never crashes on control bytes, but for consistency with the
    FDX path they should still be stripped rather than written through raw."""
    elements = [
        ScreenplayElementLike(
            element_type="action", text="bad\x01byte\x0bhere", order_index=0
        ),
    ]
    doc = _script_doc(elements)

    fountain_text = render_fountain(doc)

    assert "badbytehere" in fountain_text
    assert "\x01" not in fountain_text
    assert "\x0b" not in fountain_text


def test_sanitize_leaves_xml_valid_whitespace_control_chars_untouched():
    """``\\t``/``\\n``/``\\r`` ARE valid in XML text content (XML 1.0 §2.2) — ``_sanitize`` must
    not strip them (only the truly XML-illegal control bytes)."""
    dangerous_text = "Line one\tTabbed\nNewline\rCarriage return"
    assert _sanitize(dangerous_text) == dangerous_text


def test_render_fountain_does_not_strip_xml_valid_whitespace_control_chars():
    """Fountain is plain text, never XML-parsed, so ``\\t``/``\\n``/``\\r`` all survive verbatim
    end to end through ``_sanitize`` and the Fountain writer."""
    dangerous_text = "Line one\tTabbed\nNewline\rCarriage return"
    elements = [
        ScreenplayElementLike(element_type="action", text=dangerous_text, order_index=0),
    ]
    doc = _script_doc(elements)

    fountain_text = render_fountain(doc)
    assert dangerous_text in fountain_text


def test_render_fdx_does_not_strip_tab_and_newline():
    """``\\t``/``\\n`` are valid XML text and must survive the FDX round trip untouched by
    ``_sanitize`` (``\\r`` is a separate, pre-existing ``screenplay_tools``/XML-parser
    line-ending normalization concern — see
    ``test_sanitize_leaves_xml_valid_whitespace_control_chars_untouched`` for proof
    ``_sanitize`` itself never touches ``\\r``)."""
    dangerous_text = "Line one\tTabbed\nNewline here"
    elements = [
        ScreenplayElementLike(element_type="action", text=dangerous_text, order_index=0),
    ]
    doc = _script_doc(elements)

    fdx_text = render_fdx(doc)
    assert dangerous_text in fdx_text

    root = ET.fromstring(fdx_text)  # noqa: S314 — parses our own just-rendered output
    texts = [t.text for t in root.iter("Text")]
    assert dangerous_text in texts
