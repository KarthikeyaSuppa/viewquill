"""Tests for the Markdown export renderer (docs/06 Phase 6 task BE-3).

No DB/app import needed here — ``render_markdown``/``write_markdown_file`` only ever see
the already-materialized ``CompiledDocument`` dataclasses from ``export_service``, so this
module builds those directly rather than going through a ``TestClient``. Uses a throwaway
temp directory (never a real app-data directory) for the ``write_markdown_file`` check,
mirroring the isolation intent of ``test_images.py``'s ``QUILLNIGHT_DATA_DIR`` pattern
without needing the DB machinery that pattern exists for.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.export_markdown import render_markdown, write_markdown_file
from app.services.export_service import (
    CompiledChapter,
    CompiledDocument,
    CompiledScene,
    ScreenplayElementLike,
)


def _prose_doc() -> CompiledDocument:
    return CompiledDocument(
        book_id="book-1",
        book_title="My Novel",
        book_type="novel",
        logline="A tale of two cities.",
        front_matter={"author": "Jane Doe"},
        cover_image_id=None,
        chapters=[
            CompiledChapter(
                title="Chapter One",
                scenes=[
                    CompiledScene(
                        title="Opening",
                        description="Once upon a time.\n\nA second paragraph.",
                    )
                ],
            ),
            CompiledChapter(
                title=None,
                scenes=[CompiledScene(title="Loose Scene", description="Floating text.")],
            ),
        ],
    )


def _script_doc() -> CompiledDocument:
    elements = [
        ScreenplayElementLike(
            element_type="scene_heading", text="int. kitchen - day", order_index=0
        ),
        ScreenplayElementLike(element_type="action", text="Jane enters.", order_index=1),
        ScreenplayElementLike(element_type="character", text="jane", order_index=2),
        ScreenplayElementLike(element_type="parenthetical", text="(annoyed)", order_index=3),
        ScreenplayElementLike(element_type="dialogue", text="Where is it?", order_index=4),
        ScreenplayElementLike(element_type="transition", text="CUT TO:", order_index=5),
    ]
    return CompiledDocument(
        book_id="book-2",
        book_title="My Script",
        book_type="movie_script",
        logline=None,
        front_matter=None,
        cover_image_id=None,
        chapters=[
            CompiledChapter(
                title=None,
                scenes=[CompiledScene(title="Scene 1", description="", elements=elements)],
            )
        ],
    )


def test_prose_renders_front_matter_and_chapter_headings() -> None:
    text = render_markdown(_prose_doc())

    assert text.startswith("---\n")
    assert "title: My Novel" in text
    assert "logline: A tale of two cities." in text
    assert "author: Jane Doe" in text

    assert "## Chapter One" in text
    assert "### Opening" in text
    assert "Once upon a time." in text
    assert "A second paragraph." in text

    # Chapterless bucket never gets a "## None" (or any) chapter heading of its own —
    # only its scene's own heading appears.
    assert "## None" not in text
    assert "### Loose Scene" in text
    assert "Floating text." in text

    # Paragraph break inside the description is passed through untouched.
    assert "Once upon a time.\n\nA second paragraph." in text


def test_script_scene_renders_elements_not_description() -> None:
    text = render_markdown(_script_doc())

    assert "### Scene 1" in text
    assert "INT. KITCHEN - DAY" in text
    assert "Jane enters." in text
    assert "JANE" in text
    assert "(annoyed)" in text
    assert "Where is it?" in text
    assert "CUT TO:" in text

    # Dialogue/parenthetical are indented under the character cue.
    lines = text.splitlines()
    jane_idx = lines.index("JANE")
    assert lines[jane_idx + 1].startswith("    ") and "annoyed" in lines[jane_idx + 1]
    assert lines[jane_idx + 2].startswith("    ") and "Where is it?" in lines[jane_idx + 2]


def test_front_matter_always_includes_title_even_without_front_matter_dict() -> None:
    doc = _script_doc()  # front_matter=None, logline=None
    text = render_markdown(doc)
    assert text.startswith("---\n")
    assert "title: My Script" in text
    assert "logline:" not in text


def test_write_markdown_file_writes_readable_file_under_book_subdir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        drafts_dir = Path(tmp)
        doc = _prose_doc()

        file_path = write_markdown_file(doc, drafts_dir)

        assert file_path.exists()
        assert file_path.parent == drafts_dir / doc.book_id
        assert file_path.suffix == ".md"
        # Filename is server-generated (uuid-based), never derived from the book title.
        assert "My Novel" not in file_path.name
        assert "my-novel" not in file_path.name.lower()

        content = file_path.read_text(encoding="utf-8")
        assert content == render_markdown(doc)
        assert "## Chapter One" in content


def test_write_markdown_file_uses_unique_filenames_per_call() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        drafts_dir = Path(tmp)
        doc = _prose_doc()

        first = write_markdown_file(doc, drafts_dir)
        second = write_markdown_file(doc, drafts_dir)

        assert first != second
        assert first.exists() and second.exists()
