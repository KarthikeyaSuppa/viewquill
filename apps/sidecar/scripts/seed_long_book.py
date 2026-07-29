"""Throwaway dev script — soak-test seeder for Phase 8 manuscript-reader perf work.

Creates ONE Book with ~40 chapters and ~80,000 words of synthetic prose (multiple
scenes per chapter, multiple blank-line-delimited paragraphs per scene, matching the
shape `export_service.build_compiled_document` / `draft_preview.py` expect scene
`description` text to have), assigns every scene into the Outline via
`POST /books/{id}/scenes/{scene_id}/assign` (proper chapter assignment, so chapters get
real titles rather than landing in the chapterless bucket), then hits
`GET /books/{book_id}/draft-preview` and reports response time + payload size.

Uses an in-process `TestClient(app)` as a context manager (so Alembic migrations run,
same pattern as `tests/test_draft_preview.py`) against a throwaway `QUILLNIGHT_DATA_DIR`
temp directory — this NEVER touches the user's real `app-data/quillnight.sqlite`. The
temp dir is deleted at the end of the run regardless of outcome.

Run from apps/sidecar:
    .venv/Scripts/python.exe scripts/seed_long_book.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="quillnight-seed-long-book-")
os.environ["QUILLNIGHT_DATA_DIR"] = _TMP_DATA_DIR
os.environ.setdefault("QUILLNIGHT_LLM_STUB", "1")
os.environ.setdefault("QUILLNIGHT_STT_STUB", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

N_CHAPTERS = 40
SCENES_PER_CHAPTER = 3
TARGET_TOTAL_WORDS = 80_000
WORDS_PER_SCENE = TARGET_TOTAL_WORDS // (N_CHAPTERS * SCENES_PER_CHAPTER)  # ~666
PARAGRAPHS_PER_SCENE = 6
WORDS_PER_PARAGRAPH = WORDS_PER_SCENE // PARAGRAPHS_PER_SCENE

_LOREM_WORDS = (
    "the quick fox ran through the misty forest while shadows lengthened across the "
    "quiet clearing and the old lantern flickered against a wall of ivy near the river "
    "bend where travelers once paused to trade stories of distant kingdoms and forgotten "
    "oaths sworn beneath a sky heavy with unspoken rain"
).split()


def _make_paragraph(seed: int, word_count: int) -> str:
    words = [_LOREM_WORDS[(seed + i) % len(_LOREM_WORDS)] for i in range(word_count)]
    sentence = " ".join(words)
    return sentence[0].upper() + sentence[1:] + "."


def _make_scene_description(seed: int) -> str:
    paragraphs = [
        _make_paragraph(seed + p * 7, WORDS_PER_PARAGRAPH) for p in range(PARAGRAPHS_PER_SCENE)
    ]
    # Blank-line-delimited paragraphs — matches export_service's expected scene shape.
    return "\n\n".join(paragraphs)


def _post(client: TestClient, path: str, json: dict | None = None) -> dict:
    resp = client.post(path, json=json if json is not None else {})
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"POST {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def main() -> None:
    with TestClient(app) as client:
        book = _post(client, "/books", {"title": "Soak Test Novel", "book_type": "story_book"})
        book_id = book["id"]

        total_words = 0
        seed = 0
        for chapter_index in range(N_CHAPTERS):
            chapter = _post(
                client,
                f"/books/{book_id}/chapters",
                {"title": f"Chapter {chapter_index + 1}", "order_index": chapter_index},
            )
            chapter_id = chapter["id"]

            for scene_index in range(SCENES_PER_CHAPTER):
                description = _make_scene_description(seed)
                total_words += len(description.split())
                seed += PARAGRAPHS_PER_SCENE * 7 + 1

                scene = _post(
                    client,
                    "/scenes",
                    {
                        "node_type": "scene",
                        "title": f"Ch{chapter_index + 1} Scene {scene_index + 1}",
                        "description": description,
                    },
                )
                scene_id = scene["id"]

                # Add to canvas first — required before the scene has any book_scene_order
                # row (mirrors tests/test_draft_preview.py's _add_to_canvas step).
                resp = client.post(f"/books/{book_id}/scenes/{scene_id}")
                if resp.status_code != 201:
                    raise RuntimeError(f"add-to-canvas failed: {resp.status_code} {resp.text}")

                outline_order_index = chapter_index * SCENES_PER_CHAPTER + scene_index
                _post(
                    client,
                    f"/books/{book_id}/scenes/{scene_id}/assign",
                    {"chapter_id": chapter_id, "outline_order_index": outline_order_index},
                )

        print(f"Seeded book {book_id!r}: {N_CHAPTERS} chapters, "
              f"{N_CHAPTERS * SCENES_PER_CHAPTER} scenes, ~{total_words} words.")

        start = time.perf_counter()
        resp = client.get(f"/books/{book_id}/draft-preview")
        elapsed = time.perf_counter() - start

        if resp.status_code != 200:
            raise RuntimeError(f"draft-preview failed: {resp.status_code} {resp.text}")

        payload = resp.content
        body = resp.json()
        chapters = body["chapters"]

        print(f"GET /books/{book_id}/draft-preview -> 200 in {elapsed * 1000:.1f} ms")
        print(f"Payload size: {len(payload):,} bytes ({len(payload) / 1024:.1f} KiB)")
        print(f"Chapters returned: {len(chapters)} (expected {N_CHAPTERS})")

        ok_order = [c["title"] for c in chapters] == [
            f"Chapter {i + 1}" for i in range(N_CHAPTERS)
        ]
        print(f"Chapter order correct: {ok_order}")

        scene_counts = [len(c["scenes"]) for c in chapters]
        ok_scene_counts = all(count == SCENES_PER_CHAPTER for count in scene_counts)
        print(
            f"All chapters have {SCENES_PER_CHAPTER} scenes: {ok_scene_counts} "
            f"(counts: min={min(scene_counts)}, max={max(scene_counts)})"
        )

        if not (ok_order and ok_scene_counts):
            raise SystemExit("Structure verification FAILED — see above.")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP_DATA_DIR, ignore_errors=True)
