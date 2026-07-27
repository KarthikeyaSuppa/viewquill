"""Fountain / Final Draft (.fdx) renderers for script book types (docs/05-EXPORT-IMPORT-
SECURITY.md format table, docs/06 Phase 6 task BE-6).

Builds one ``screenplay_tools`` ``Script`` object from a ``CompiledDocument`` (see
``app.services.export_service``) and hands that SAME ``Script`` object to the library's own
Fountain writer (``screenplay_tools.fountain.writer.Writer``) and FDX writer
(``screenplay_tools.fdx.writer.Writer``) — this module never hand-builds Fountain text or XML
markup itself; the library's writers own all serialization.

Only ever called for ``movie_script``/``short_film_script`` book types. The caller (BE-7's
export router) is expected to have already called ``export_service.ensure_format_allowed()``,
but both render functions here defensively re-check and raise the same
``ValueError("FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE")`` export_service uses, rather than trusting
the caller silently.

SECURITY (reviewer-flagged — FDX is XML, injection risk from user-controlled text):
``screenplay_tools.fdx.writer.Writer.write`` (read directly from the installed package,
``.venv/Lib/site-packages/screenplay_tools/fdx/writer.py``) builds the document with
``xml.etree.ElementTree`` — ``ET.SubElement(...)`` for structure and plain ``element.text =
text`` assignment for every paragraph's content — then serializes with ``ET.tostring`` (via
``xml.dom.minidom.parseString(...).toprettyxml(...)`` for pretty-printing). ``ElementTree``'s
serializer escapes ``&``/``<``/``>`` in text content automatically; it is never built via raw
f-string/``%``-formatted XML. This module supplies zero raw XML of its own — every piece of
user-controlled text (scene/chapter titles, screenplay element text, scene descriptions) only
ever reaches the FDX output by being assigned to a ``screenplay_tools`` ``Element`` subclass's
text/name, which the library's own ``ElementTree``-based writer then escapes on serialization.
That means **case (a)** from the task brief applies: correctness here rests on the library's
writer doing its own escaping (verified above by reading its source and by this task's
``tests/test_export_fountain.py`` round-tripping ``<``/``&``/``"`` through ``ET.fromstring``),
not on any manual escaping performed in this module.

BUGFIX (reviewer-flagged — control characters are not "escaping", they're outright XML-illegal):
the analysis above covers ``&``/``<``/``>``, which ``ElementTree`` escapes correctly. It does
NOT cover XML 1.0's ``Char`` production (§2.2), which excludes every C0 control byte except
``\t``/``\n``/``\r`` (i.e. ``\x00-\x08``, ``\x0B``, ``\x0C``, ``\x0E-\x1F``). ``ElementTree``
neither escapes nor rejects these — it writes them through raw — so
``xml.dom.minidom.parseString()`` (used by the FDX writer to pretty-print) raises
``xml.parsers.expat.ExpatError: not well-formed (invalid token)`` on any of them, taking down
the entire export for one stray byte plausibly introduced by dictation/STT, OCR-sourced paste,
or a corrupted clipboard paste. ``_sanitize()`` below strips these bytes from every
user-controlled text field (scene/chapter titles, screenplay element text, scene descriptions)
at the single point they're read into ``screenplay_tools`` element constructors (``_append_scene``/
``_append_chapter``), for both renderers — Fountain doesn't crash on them, but there's no reason
to write a stray control byte through to a plain-text file either.

Fountain (plain text) has a much lower-severity, non-XML analogue: a user's screenplay-element
text could theoretically contain sequences Fountain treats as directives if line-broken just
right (e.g. a line starting with ``#`` looks like a ``Section``, ``!`` like a forced action,
``[[``/``]]`` like a note, ``/*``/``*/`` like a boneyard). This module never re-parses its own
output — it builds ``Script.elements`` directly from ``screenplay_tools`` element *objects*
(``Action``/``Dialogue``/etc.), not by concatenating raw strings the Fountain *parser* would
later re-interpret — so text is written out via ``Writer._write_elem`` verbatim inside the
already-decided element type (a ``Dialogue`` line's text is always written as dialogue, never
reinterpreted as a heading). The one caveat, inherent to the library itself and not introduced
here: ``Element.text`` (used by both writers) strips embedded ``[[N]]``/``/*N*/`` reference
markers via regex before returning — text containing literal substrings that happen to match
those patterns would render without them. This is a pre-existing ``screenplay_tools`` behavior
on its ``Element.text`` property, not something this module's mapping causes or can avoid
without bypassing the library's own text accessor.
"""

from __future__ import annotations

import re

from screenplay_tools.fdx.writer import Writer as FdxWriter
from screenplay_tools.fountain.writer import Writer as FountainWriter
from screenplay_tools.screenplay import (
    Action,
    Character,
    Dialogue,
    Parenthetical,
    SceneHeading,
    Script,
    Transition,
)

from app.services.export_service import CompiledChapter, CompiledDocument, CompiledScene

_SCRIPT_BOOK_TYPES = {"movie_script", "short_film_script"}

# XML 1.0 (§2.2) only allows Char ::= #x9 | #xA | #xD | [#x20-...] — i.e. every C0 control byte
# EXCEPT tab/newline/carriage-return is illegal in XML text content. ``ElementTree`` escapes
# &/</> but neither escapes nor rejects these bytes; ``xml.dom.minidom.parseString`` (used by
# ``screenplay_tools.fdx.writer.Writer.write`` to pretty-print) then raises
# ``xml.parsers.expat.ExpatError: not well-formed (invalid token)`` on them, taking down the
# whole export for one stray control byte (plausible from dictation/STT, OCR paste, or a
# corrupted clipboard paste into a scene description or screenplay element). Stripped here,
# before any user-controlled text reaches a ``screenplay_tools`` element constructor, for both
# renderers — Fountain doesn't crash on these bytes, but there's no reason to let them through
# to a plain-text file either.
_XML_INVALID_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _sanitize(text: str) -> str:
    """Strips XML-illegal control characters from ``text``. ``\\t``/``\\n``/``\\r`` are valid
    XML text and are intentionally left untouched."""
    return _XML_INVALID_CONTROL_CHARS.sub("", text)

# Maps ``ScreenplayElement.element_type`` (docs/03-DATA-MODEL.md `screenplay_elements` CHECK
# constraint) to a ``screenplay_tools`` element factory. Two types have no exact
# ``screenplay_tools`` equivalent — both fall back to a type that preserves every character of
# the user's text (no data loss), at the cost of losing type-specific formatting:
#   - "shot" (e.g. "CLOSE ON:") -> Action: the library has no dedicated shot element.
#   - "dual_dialogue" -> Dialogue: the flat ``ScreenplayElementLike`` list carries no pairing
#     info to the sibling ``Character`` cue it plays opposite, so screenplay_tools's
#     ``Character(dual=True)``/side-by-side FDX layout can't be reconstructed from this shape.
_ELEMENT_FACTORIES = {
    "scene_heading": lambda text: SceneHeading(text),
    "action": lambda text: Action(text),
    "character": lambda text: Character(name=text),
    "dialogue": lambda text: Dialogue(text),
    "parenthetical": lambda text: Parenthetical(text),
    "transition": lambda text: Transition(text),
    "shot": lambda text: Action(text),
    "dual_dialogue": lambda text: Dialogue(text),
}


def _ensure_script_book_type(doc: CompiledDocument) -> None:
    if doc.book_type not in _SCRIPT_BOOK_TYPES:
        raise ValueError("FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE")


def _append_scene(script: Script, scene: CompiledScene) -> None:
    """Appends one ``CompiledScene`` onto ``script.elements``.

    A scene heading is only synthesized from ``scene.title`` if the scene's own elements don't
    already open with one — i.e. only when ``elements`` is empty or its first entry isn't
    ``element_type == "scene_heading"``. ``scene.description`` (the prose notes that coexist
    with structured elements — see ``export_service.build_compiled_document``'s docstring) is
    never dropped: if present, it's appended as a plain ``Action`` paragraph immediately after
    the heading and before the scene's own elements, so it survives the export even though
    Fountain/FDX have no dedicated "scene notes" concept.
    """
    elements = scene.elements
    has_leading_heading = bool(elements) and elements[0].element_type == "scene_heading"
    if not has_leading_heading:
        script.elements.append(SceneHeading(_sanitize(scene.title or "")))

    if scene.description:
        script.elements.append(Action(_sanitize(scene.description)))

    for element in elements:
        factory = _ELEMENT_FACTORIES.get(element.element_type, Action)
        script.elements.append(factory(_sanitize(element.text)))


def _build_script(doc: CompiledDocument) -> Script:
    """Builds one ``screenplay_tools`` ``Script`` from every chapter/scene/element in ``doc``,
    in the same order ``export_service.build_compiled_document`` produced them."""
    script = Script()
    for chapter in doc.chapters:
        _append_chapter(script, chapter)
    return script


def _append_chapter(script: Script, chapter: CompiledChapter) -> None:
    if chapter.title:
        # Rendered as a centered ``Action`` line rather than a screenplay_tools ``Section`` —
        # the FDX writer's element loop explicitly skips ``ElementType.SECTION`` (see
        # ``screenplay_tools/fdx/writer.py``), which would silently drop chapter titles from
        # FDX output only (while still showing up in Fountain). An ``Action`` line renders,
        # and survives, in both formats.
        heading = Action(_sanitize(chapter.title))
        heading.centered = True
        script.elements.append(heading)

    for scene in chapter.scenes:
        _append_scene(script, scene)


def render_fountain(doc: CompiledDocument) -> str:
    """Renders ``doc`` to a Fountain-format string via ``screenplay_tools.fountain.writer``."""
    _ensure_script_book_type(doc)
    script = _build_script(doc)
    return FountainWriter().write(script)


def render_fdx(doc: CompiledDocument) -> str:
    """Renders ``doc`` to a Final Draft ``.fdx`` XML string via ``screenplay_tools.fdx.writer``
    — see this module's docstring for why every user-controlled string reaching this output is
    safely escaped by construction (the library's own ``xml.etree.ElementTree``-based writer)."""
    _ensure_script_book_type(doc)
    script = _build_script(doc)
    return FdxWriter().write(script)
