"""Tests for ``export_docx.render_docx`` (docs/06 Phase 6 task BE-4).

No DB/app import needed — ``export_docx`` is a pure ``CompiledDocument -> bytes`` transform,
so these tests build ``CompiledDocument``/``CompiledChapter``/``CompiledScene`` dataclasses
by hand and never touch QUILLNIGHT_DATA_DIR or the FastAPI app.
"""

from __future__ import annotations

import io
from pathlib import Path

from docx import Document as DocxDocument

from app.services.export_docx import render_docx
from app.services.export_service import (
    CompiledChapter,
    CompiledDocument,
    CompiledScene,
    ScreenplayElementLike,
)


def _prose_document(front_matter: dict | None = None) -> CompiledDocument:
    return CompiledDocument(
        book_id="book-1",
        book_title="The Long Night",
        book_type="novel",
        logline="A quiet town keeps a loud secret.",
        front_matter=front_matter,
        cover_image_id=None,
        chapters=[
            CompiledChapter(
                title="Chapter One",
                scenes=[
                    CompiledScene(
                        title="Opening",
                        description="It was dark.\n\nThen it got darker.",
                        elements=[],
                    )
                ],
            ),
            CompiledChapter(
                title=None,  # chapterless bucket — must render with no heading
                scenes=[
                    CompiledScene(title="Loose scene", description="Unplaced content.", elements=[])
                ],
            ),
        ],
    )


def _script_document() -> CompiledDocument:
    return CompiledDocument(
        book_id="book-2",
        book_title="Neon Alley",
        book_type="movie_script",
        logline=None,
        front_matter=None,
        cover_image_id=None,
        chapters=[
            CompiledChapter(
                title=None,
                scenes=[
                    CompiledScene(
                        title="INT. ALLEY - NIGHT",
                        description="",
                        elements=[
                            ScreenplayElementLike(
                                element_type="scene_heading",
                                text="INT. ALLEY - NIGHT",
                                order_index=0,
                            ),
                            ScreenplayElementLike(
                                element_type="action",
                                text="Rain hammers the pavement.",
                                order_index=1,
                            ),
                            ScreenplayElementLike(
                                element_type="character", text="MAYA", order_index=2
                            ),
                            ScreenplayElementLike(
                                element_type="parenthetical", text="(whispering)", order_index=3
                            ),
                            ScreenplayElementLike(
                                element_type="dialogue", text="We shouldn't be here.", order_index=4
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def _all_paragraph_text(document: DocxDocument) -> str:
    return "\n".join(p.text for p in document.paragraphs)


def test_prose_book_renders_valid_docx_with_expected_content():
    result = render_docx(_prose_document())
    assert isinstance(result, bytes)
    assert len(result) > 0

    opened = DocxDocument(io.BytesIO(result))
    full_text = _all_paragraph_text(opened)

    assert "The Long Night" in full_text
    assert "A quiet town keeps a loud secret." in full_text
    assert "Chapter One" in full_text
    assert "Opening" in full_text
    assert "It was dark." in full_text
    assert "Then it got darker." in full_text
    assert "Loose scene" in full_text
    assert "Unplaced content." in full_text

    # Split-on-blank-line behavior: the two description sentences land in separate paragraphs.
    paragraph_texts = [p.text for p in opened.paragraphs]
    assert "It was dark." in paragraph_texts
    assert "Then it got darker." in paragraph_texts

    # Roughly enough paragraphs to cover title/logline/2 headings/2 scene headings/2 body paras.
    assert len(opened.paragraphs) >= 7


def test_prose_front_matter_renders_present_keys_and_coerces_non_strings():
    front_matter = {
        "subtitle": "A Novel",
        "author": "J. Doe",
        "tags": ["gothic", "slow-burn"],  # non-string value must not crash
    }
    result = render_docx(_prose_document(front_matter=front_matter))

    opened = DocxDocument(io.BytesIO(result))
    full_text = _all_paragraph_text(opened)

    assert "A Novel" in full_text
    assert "Author: J. Doe" in full_text
    assert "Tags:" in full_text
    assert "gothic" in full_text


def test_script_book_uses_courier_and_indentation():
    result = render_docx(_script_document())
    opened = DocxDocument(io.BytesIO(result))

    assert opened.styles["Normal"].font.name == "Courier New"
    assert opened.styles["Normal"].font.size is not None
    assert opened.styles["Normal"].font.size.pt == 12

    full_text = _all_paragraph_text(opened)
    assert "Neon Alley" in full_text
    assert "INT. ALLEY - NIGHT" in full_text
    assert "Rain hammers the pavement." in full_text
    assert "MAYA" in full_text
    assert "(whispering)" in full_text
    assert "We shouldn't be here." in full_text

    # Margins set per BE-4's industry-adjacent spec.
    section = opened.sections[0]
    assert section.left_margin.inches == 1.5
    assert section.right_margin.inches == 1.0

    # Character line should be indented further than action/scene_heading (flush left).
    character_paragraph = next(p for p in opened.paragraphs if p.text == "MAYA")
    action_paragraph = next(p for p in opened.paragraphs if "Rain hammers" in p.text)
    assert character_paragraph.paragraph_format.left_indent.inches == 2.0
    assert action_paragraph.paragraph_format.left_indent.inches == 0.0


def test_missing_cover_image_path_does_not_crash():
    missing_path = Path("this/path/definitely/does/not/exist.png")
    result = render_docx(_prose_document(), cover_image_path=missing_path)
    assert isinstance(result, bytes)
    assert len(result) > 0

    opened = DocxDocument(io.BytesIO(result))
    assert "The Long Night" in _all_paragraph_text(opened)


def test_corrupt_cover_image_file_does_not_crash(tmp_path):
    corrupt_image_path = tmp_path / "cover.png"
    corrupt_image_path.write_bytes(b"not actually a png")

    result = render_docx(_prose_document(), cover_image_path=corrupt_image_path)
    assert isinstance(result, bytes)
    assert len(result) > 0

    opened = DocxDocument(io.BytesIO(result))
    assert "The Long Night" in _all_paragraph_text(opened)
