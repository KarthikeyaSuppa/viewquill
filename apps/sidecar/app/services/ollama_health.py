"""Lightweight Ollama reachability probe for /health.

Uses stdlib urllib (no extra dependency) with a short timeout so the health check never
blocks. Full LLM orchestration (LiteLLM-backed, streaming, keep-warm) arrives in Phase 2 —
this is only a "is the runtime up?" ping. Ollama being down is expected until it's bundled.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.config import get_settings
from app.models.schemas import OllamaHealth


def check_ollama(timeout: float = 0.6) -> OllamaHealth:
    base = get_settings().ollama_base_url
    url = f"{base}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (localhost only)
            payload = json.loads(resp.read() or b"{}")
        models = [m.get("name") for m in payload.get("models", [])]
        detail = f"{len(models)} model(s) available" if models else "no models pulled yet"
        return OllamaHealth(reachable=True, base_url=base, detail=detail)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return OllamaHealth(reachable=False, base_url=base, detail=f"unreachable: {exc}")
