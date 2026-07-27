"""Markdown renderer for the compiled export pipeline (docs/06 Phase 6 task BE-3).

Consumes the format-agnostic ``CompiledDocument`` built by
``app.services.export_service.build_compiled_document`` and renders it to a Markdown
string via a Jinja2 template (``app/templates/draft.md.j2``), then optionally writes that
string to a server-generated file under ``drafts_dir``. This module does NOT read the DB
or hold any ORM state — it only ever sees the already-materialized dataclasses, matching
``export_service``'s "fully materialized, not lazy ORM" contract.

Not a Fountain/FDX renderer: script book types (``movie_script``/``short_film_script``) get
a simple, readable plain-text/Markdown approximation of their ``ScreenplayElement`` rows
(uppercase scene headings/character cues, indented dialogue/parenthetical, plain action/
transition/shot/dual_dialogue lines) — real screenplay-format export is BE-6's job.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.db.base import new_uuid
from app.services.export_service import CompiledDocument, ScreenplayElementLike

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Markdown/plain-text output, not HTML — autoescape is deliberately off (there's no HTML/XML
# injection surface here, unlike a browser-rendered template). trim_blocks/lstrip_blocks so a
# `{% ... %}` control-flow line in draft.md.j2 never leaves a stray blank line behind; only
# the blank lines explicitly written in the template become output spacing.
_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=(".j2",), default=False),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)

_SCRIPT_BOOK_TYPES = {"movie_script", "short_film_script"}

# ── scene body rendering ─────────────────────────────────────────────────────────

_DIALOGUE_INDENT = "    "

_UPPERCASE_TYPES = {"scene_heading", "character"}
_INDENTED_TYPES = {"dialogue", "parenthetical"}
# Everything else (action/transition/shot/dual_dialogue) renders as its own plain line —
# handled by the else-branch below, not listed explicitly.


def _render_script_scene_body(elements: list[ScreenplayElementLike]) -> str:
    """Simple, readable plain-text rendering of one scene's ``ScreenplayElement`` rows
    (already in ``order_index`` order — see ``export_service.build_compiled_document``).
    Not real screenplay formatting, just enough structure to be readable (BE-6 owns the
    actual Fountain/FDX export)."""
    lines: list[str] = []
    for element in elements:
        text = element.text or ""
        if element.element_type in _UPPERCASE_TYPES:
            lines.append(text.upper())
        elif element.element_type in _INDENTED_TYPES:
            lines.append(f"{_DIALOGUE_INDENT}{text}")
        else:  # action, transition, shot, dual_dialogue
            lines.append(text)
    return "\n".join(lines)


def _render_prose_scene_body(description: str) -> str:
    """Pass-through — a scene's prose ``description`` is never reformatted, only carried
    through as-is (existing paragraph breaks preserved)."""
    return description


# ── YAML front-matter ────────────────────────────────────────────────────────────

_YAML_RESERVED_SCALARS = {"true", "false", "null", "~", "yes", "no"}
_YAML_SPECIAL_PREFIXES = tuple("!&*-?|>%@`\"'#,[]{}")


def _yaml_needs_quoting(text: str) -> bool:
    """Conservative check — not a full YAML-spec scanner, just enough to keep front-matter
    values that a downstream tool re-parses as YAML unambiguous. Errs on the side of
    quoting rather than risking an unquoted value that a naive parser misreads."""
    if text == "" or text != text.strip():
        return True
    if text.lower() in _YAML_RESERVED_SCALARS:
        return True
    if text.startswith(_YAML_SPECIAL_PREFIXES):
        return True
    if "#" in text or "\n" in text:
        return True
    if ":" in text and (": " in text or text.endswith(":")):
        return True
    try:
        float(text)
    except ValueError:
        pass
    else:
        return True
    return False


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if _yaml_needs_quoting(text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return text


def _build_front_matter_lines(doc: CompiledDocument) -> list[str]:
    """``title`` (from ``doc.book_title``) and ``logline`` (if present) are authoritative and
    always come first; any other ``doc.front_matter`` keys follow in their existing order.
    A ``title`` key is always present, so this always returns a non-empty list — the block is
    effectively always emitted, which satisfies both "always include title" and "only emit
    the block if it has content" from the task at once."""
    ordered: dict[str, Any] = {"title": doc.book_title}
    if doc.logline:
        ordered["logline"] = doc.logline
    if doc.front_matter:
        for key, value in doc.front_matter.items():
            if key in ("title", "logline"):
                continue  # already set above from the authoritative fields
            ordered[key] = value
    return [f"{key}: {_yaml_scalar(value)}" for key, value in ordered.items()]


# ── public API ───────────────────────────────────────────────────────────────────


def render_markdown(doc: CompiledDocument) -> str:
    """Renders ``doc`` to a Markdown string via ``app/templates/draft.md.j2``.

    Chapterless scenes' bucket (``CompiledChapter(title=None, ...)``) never prints a
    heading line for itself — only its scenes' own ``### <title>`` headings appear. Script
    book types (``movie_script``/``short_film_script``) get each scene's
    ``ScreenplayElement`` rows rendered as a simple plain-text block instead of the plain
    prose ``description`` paragraph; every other book type gets the prose paragraph as-is.
    """
    is_script = doc.book_type in _SCRIPT_BOOK_TYPES

    chapters_ctx = []
    for chapter in doc.chapters:
        scenes_ctx = []
        for scene in chapter.scenes:
            body = (
                _render_script_scene_body(scene.elements)
                if is_script
                else _render_prose_scene_body(scene.description)
            )
            scenes_ctx.append({"title": scene.title, "body": body})
        chapters_ctx.append({"title": chapter.title, "scenes": scenes_ctx})

    template = _ENV.get_template("draft.md.j2")
    rendered = template.render(
        front_matter_lines=_build_front_matter_lines(doc),
        chapters=chapters_ctx,
    )
    # Collapse any run of 3+ blank lines the template's spacing rules can produce for
    # chapters/scenes with empty bodies down to a single blank line, and ensure exactly one
    # trailing newline — cosmetic only, never touches real content lines.
    lines = rendered.splitlines()
    collapsed: list[str] = []
    for line in lines:
        if line == "" and len(collapsed) >= 2 and collapsed[-1] == "" and collapsed[-2] == "":
            continue
        collapsed.append(line)
    return "\n".join(collapsed).rstrip("\n") + "\n"


def write_markdown_file(doc: CompiledDocument, drafts_dir: Path) -> Path:
    """Renders ``doc`` and writes it to ``drafts_dir/<book_id>/<uuid>.md``, creating the
    per-book directory if needed. The filename is ALWAYS server-generated (``new_uuid()``)
    — never derived from ``doc.book_title`` (untrusted/could contain path-unsafe characters)
    — mirroring ``images_service.save_image``'s server-generated-filename convention."""
    content = render_markdown(doc)
    book_dir = drafts_dir / doc.book_id
    book_dir.mkdir(parents=True, exist_ok=True)
    file_path = book_dir / f"{new_uuid()}.md"
    file_path.write_text(content, encoding="utf-8")
    return file_path
