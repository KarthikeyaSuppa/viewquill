"""Quillnight FastAPI sidecar — owns all domain logic, data, and AI orchestration.

The Tauri/Rust shell spawns and supervises this process; the React frontend talks to
it exclusively over local HTTP (127.0.0.1). See docs/02-ARCHITECTURE.md.
"""

__version__ = "0.0.0"
