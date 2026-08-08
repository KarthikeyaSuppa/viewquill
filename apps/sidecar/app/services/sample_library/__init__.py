"""Sample library package: seeds a fresh Quillnight install with demo Books.

This package owns two concerns:

1. **Data** — ``content.py``'s pure-data spec (four demo Books' worth of Scenes,
   Codex entries, canvas layouts, relationships, etc.) plus ``seeder.py``'s
   ``seed_sample_library``, which turns that spec into real rows exactly once
   per install (idempotent — see ``seeder.py``'s module docstring for the guard).
2. **Assets** — deterministic placeholder artwork (``images.py``) for those
   demo Books' covers/scene art/character portraits. Real PNG bytes are
   generated (not fabricated DB rows pointing at nonexistent files) because
   no ``<img>`` consumer in the frontend has an ``onError`` fallback — a
   missing file on disk would render a broken-image glyph.

Re-exported here so callers only need
``from app.services.sample_library import seed_sample_library`` (this is exactly
how ``app/main.py``'s startup lifespan imports it).
"""

from __future__ import annotations

from app.services.sample_library.seeder import seed_sample_library

__all__ = ["seed_sample_library"]
