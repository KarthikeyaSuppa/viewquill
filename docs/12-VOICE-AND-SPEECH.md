# Voice & Speech

Speech runs in both directions in Quillnight, and for a dyslexic writer both are first-class accessibility, not conveniences:

- **Dictation (speech → text)**: speak a raw thought instead of typing it; the transcript lands in the focused field; Enhance cleans it up. Often the single biggest friction-remover — the idea arrives at speaking speed, the AI handles the spelling.
- **Read-aloud (text → speech)**: hear your own draft read back, with word-by-word highlighting — hearing errors that eyes skip is a classic, effective proofreading technique for dyslexic writers.

A note on **Larynx** (which the user runs locally today): Larynx is a *text-to-speech* engine — the read-aloud direction — and its own author (Michael Hansen / synesthesiam) succeeded it with **Piper**, which is what this design uses for the quality voice. Dictation is the opposite direction and needs a speech-*recognition* engine (the Whisper/Parakeet family below). Both directions are covered; the Larynx instinct ("use the local thing") was exactly right, just pointed at one half of the picture.

---

## 1. Dictation (STT)

### Engine matrix

| Engine | Where it runs | Verdict |
|---|---|---|
| **NVIDIA Parakeet-TDT 0.6B v3** via `onnx-asr` (PyPI: `onnx-asr[cpu,hub]`) | **CPU — primary local engine** | ✅ **Chosen.** Top open-model word-error-rate, 25 languages, real-time on CPU, natively handles the 20–30s chunks push-to-talk produces. Runs on CPU → **zero VRAM contention** with the chat model, and avoids GPU-runtime packaging entirely. Plain `pip install`, no NeMo. |
| whisper.cpp (Vulkan backend) | GPU, single sidecar exe | 📋 Documented alternative: ~70–90% of CUDA speed with *no* cuDNN/CUDA toolkit to ship — very Tauri-sidecar-friendly. Fallback if Parakeet's PyInstaller packaging spike fails. |
| faster-whisper (CTranslate2) | GPU | ❌ Rejected for this app: best-in-class on paper (large-v3-turbo int8 ≈1.5GB VRAM), but it competes with the chat model for 4GB VRAM, and CTranslate2 ≥4.5 requires bundling ~1GB of cuDNN 9 DLLs (the "cudnn_ops64_9.dll not found" packaging trap). |
| **Groq `whisper-large-v3-turbo`** | Cloud (user's free key) | ✅ **Online-mode engine.** ~200× real-time (latency ≈ upload time). Free tier: ~2,000 requests/day, 7,200 audio-seconds/hour, 25MB/file — ample for dictation, and why local stays primary. |

Routing follows the exact same **Offline / Online / Hybrid** semantics as text AI ([08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md)): Offline → Parakeet only; Online → Groq; Hybrid → Groq preferred, instant local fallback on failure/rate-limit. The provider indicator shows which engine transcribed.

### Capture design

- **Not the browser.** MediaRecorder inside Tauri's WebView2 has well-documented Windows permission flakiness. Audio capture happens **natively in the Python sidecar** via `sounddevice` (PyPI, PortAudio) with simple start/stop endpoints; the frontend only sends button/hotkey state.
- **Push-to-talk, record-then-transcribe** — hold the hotkey (default `Ctrl+Space`, configurable; also a mic button on every text field), speak one thought (10–30s), release. A complete utterance transcribes locally in ~1–3s. This beats streaming transcription for note dictation: Whisper-family models aren't streaming architectures, and a thought is a natural unit.
- **Silero VAD** (voice-activity detection, PyPI) auto-stops after trailing silence and trims lead/tail silence — so holding the key slightly too long never pollutes the transcript.
- **Raw audio is kept** — every dictation saves its audio file plus transcript to `voice_notes` ([03-DATA-MODEL.md](03-DATA-MODEL.md)) with a status (`transcribed` / `attached` / `discarded`). Never-lose-data applies to your voice too: a mis-transcription can always be re-listened and re-transcribed later, including with a better future engine.

### The flow

```
Hold hotkey → speak → release (or VAD auto-stop)
  → sidecar transcribes (Parakeet local / Groq online)
  → transcript inserted at cursor in the focused field
  → [optional, one keystroke] Enhance cleans grammar/punctuation
  → raw audio + transcript stored in voice_notes
```

- **v1.0 (core)**: the flow above into any text field — node titles/descriptions, codex fields, image descriptions.
- **v1.1 — Brain-dump mode**: talk for as long as you like about anything ("okay so there's this scene where…"); the AI splits the ramble into **multiple draft nodes** (title + description each, via the same structured-output pipeline in [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md)), presented for review before anything is created — the Accept/Reject rule applies to node creation too.
- The firefly mascot's "thinking" state ([10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §6) doubles as the recording/transcribing indicator — pulsing while listening, scribbling while transcribing.

## 2. Read-aloud (TTS)

Two voices for two jobs:

| | Proofread mode (karaoke) | Listen-through mode |
|---|---|---|
| Engine | **Web Speech API** (`speechSynthesis`, built into WebView2 — zero packaging) | **Piper TTS** — neural, natural 22kHz voices |
| Why | Its `boundary` events fire **per word**, driving karaoke-style word highlighting via `charIndex` — the proofreading feature; Piper can't do this (no word timestamps) | Much more pleasant voice for hearing a whole chapter; worth the extra process |
| Word highlighting | ✅ | — (paragraph-level highlight only) |

**Web Speech implementation notes** (verified quirks): use **local Windows (SAPI/OneCore) voices** — Edge's online "Natural" voices ignore pitch settings and fire events unreliably; sentence boundaries report `charLength: 0` (handle it); chunk utterances per paragraph so pause/resume and highlight-sync stay stable.

**Piper licensing constraint (important):** the original MIT `rhasspy/piper` was **archived in October 2025**; the actively maintained successor is **`OHF-Voice/piper1-gpl`** (`pip install piper-tts`, Windows-supported) — which is **GPL-3.0**. Rule, recorded here and in [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md): **Piper runs as a separate, standalone sidecar process communicating over stdin/HTTP — never imported into or linked with Quillnight's own code** — keeping the GPL boundary at the process line, the same isolation pattern as everything else in this architecture. Piper is a v1.1 deliverable; v1.0 read-aloud is Web Speech only (which is also the karaoke engine forever).

Read-aloud is reachable from every prose surface: node descriptions, codex entries, and — most importantly — the Final Draft tab, where "listen to the chapter" is the proofreading pass.

## 3. Settings surface

Under **Settings → Voice**:
- Dictation: on/off, hotkey, engine mode indicator (inherits AI Mode), input device picker, VAD sensitivity.
- Read-aloud: voice picker (Web Speech local voices; Piper voices once installed in v1.1), speed, highlight style (word / sentence).
- All voice features are individually disableable; nothing records except while the push-to-talk key is held (a visible recording indicator is always shown while capturing — trust rule).

## 4. Phase 0 spike (added to [06-ROADMAP.md](06-ROADMAP.md))

Parakeet via `onnx-asr` on the target CPU: (a) real-time-or-better transcription of a 30s clip, (b) survives PyInstaller packaging (onnxruntime DLL collection is the known risk), (c) `sounddevice` capture works from the packaged sidecar. Pass/fail artifact recorded in [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md); whisper.cpp-Vulkan is the documented fallback.

## Sources

[onnx-asr](https://github.com/istupakov/onnx-asr) · [Parakeet-TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) · [faster-whisper cuDNN packaging issue](https://github.com/SYSTRAN/faster-whisper/issues/1230) · [local STT comparison 2026](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026) · [Groq speech-to-text](https://console.groq.com/docs/speech-to-text) · [Tauri microphone issues](https://github.com/tauri-apps/tauri/issues/10898) · [tauri-plugin-mic-recorder (considered)](https://github.com/ayangweb/tauri-plugin-mic-recorder) · [Silero VAD](https://github.com/snakers4/silero-vad) · [piper1-gpl (active fork)](https://github.com/OHF-Voice/piper1-gpl) · [archived rhasspy/piper](https://github.com/rhasspy/piper) · [speechSynthesis boundary event](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/boundary_event) · [JS TTS quirks](https://codersblock.com/blog/javascript-text-to-speech-and-its-many-quirks/)
