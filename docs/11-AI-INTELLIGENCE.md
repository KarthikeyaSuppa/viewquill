# AI Intelligence Architecture

This document upgrades the AI layer beyond "call the model with some context" ([04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md) covers the plumbing; this covers the *intelligence*): which model, how context is retrieved (RAG/GraphRAG-lite), how repeat calls get fast (prefix caching / local CAG), how reasoning is structured on small models (two-pass CoT), and how hallucinated output is mechanically filtered (quote verification, self-consistency voting). Every pattern here was chosen against July-2026 research and the actual hardware (RTX 3050 4GB VRAM, 16GB RAM); rejected patterns are recorded at the end so they don't get re-proposed.

---

## 1. Model selection (supersedes the original Mistral-7B choice)

The original plan (early-2026) chose Mistral-7B-Instruct. It's now **clearly outdated** — superseded twice within Mistral's own lineup, and 2026's 4B-class models beat it on instruction-following and JSON reliability at *lower* memory cost. Critically, on a 4GB-VRAM card, a model that **fits VRAM entirely** beats a bigger partially-offloaded one on both speed and consistency.

| Role | Model | Size (Q4) | VRAM fit | Why |
|---|---|---|---|---|
| **Default (all tasks)** | `qwen3.5:4b` | ~3.4GB | **Fully GPU-resident** | Best-in-class instruction-following and JSON-schema adherence in its class; solid prose; fast |
| **Grammar specialist (optional alternate)** | `gemma4:e4b` | ~4.5GB | Near-full (slight offload) | The Gemma line tops ≤9B grammar-correction studies (17-model multilingual GEC eval, arXiv 2505.06004) even unfine-tuned |
| **Quality toggle (optional)** | `qwen3.5:9b` | ~6.6GB | Partial offload | For deliberate heavy passes where the user accepts slower output |

- All three are **runtime settings, never hardcoded** (`app_settings`), same rule as the Groq model name — the local-model landscape moves too fast for compile-time choices.
- **Phase 0 spike** measures tok/s + a quick grammar-quality eval for all three on the actual machine before the default is locked (see [06-ROADMAP.md](06-ROADMAP.md)).
- Availability of these exact tags on Ollama's official library must be verified at Phase 0 ([07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md)); if a tag has churned, pick the nearest current equivalent by the same criteria (fits 4GB fully; instruction-following-first).
- Groq cloud models for Online/Hybrid mode are unchanged ([08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md)).

## 2. The semantic layer (RAG inside the existing SQLite)

A new sidecar service (`semantic_search.py`) adds retrieval over everything the user writes — with **zero new services or databases**:

- **Vector store: `sqlite-vec`** (v0.1.9, Mozilla Builders-sponsored, official PyPI Windows wheel). Vectors live in `vec0` virtual tables **inside the same SQLite file and transaction space** as scenes/codex — one DB, one backup artifact, SQL JOINs between vectors and story entities. Brute-force search (no ANN) is single-digit milliseconds at this app's scale (thousands of chunks, not millions), so no index tuning exists to get wrong.
- **Embedding model: `qwen3-embedding:0.6b`** via Ollama (639MB, 1024-dim, MRL-truncatable to 512/256 to shrink the DB, 32k context, 100+ languages). Fallback: `embeddinggemma`. Avoid `mxbai-embed-large` (512-token context truncates scene-sized chunks) and dated `nomic-embed-text`.
- **VRAM discipline (the trick that makes this work on 4GB)**: the embedder is **pinned to CPU** with `options: {"num_gpu": 0}` and a long `keep_alive` — a 600MB embedder embeds scene-sized chunks fast on CPU, and the chat model keeps every one of its GPU layers. No eviction, no thrash. 16GB RAM holds both comfortably.
- **Chunking**: scenes/codex entries are natural semantic units — embed per entity (title + body), no arbitrary splitting. Embeddings are **derived data**: rebuildable from text at any time, regenerated after `.quillproj` import, and **never included in export bundles** ([05-EXPORT-IMPORT-SECURITY.md](05-EXPORT-IMPORT-SECURITY.md)).

### Hybrid retrieval (vectors + keywords, fused)

Embeddings fuzz proper nouns — exactly the terms a writer searches ("Elyndra", "the Ashgate"). So retrieval is always **hybrid**:

1. **FTS5** (SQLite's built-in BM25 full-text index — already free) over titles/bodies/codex names.
2. **vec0 KNN** over embeddings.
3. Fused by **Reciprocal Rank Fusion**: `score = Σ 1/(60 + rank)` per result across both lists — no score normalization needed, one SQL CTE, with the keyword leg weighted up when the query contains known entity names.

### What the semantic layer powers (v1.1 phase)

- **Semantic search**: "find scenes where someone betrays someone" — across the whole library.
- **Auto codex-link suggestions**: writing a scene that mentions Elena → "Link Elena to this scene?" (retrieval + name match, one click, never automatic).
- **Similar-scene / duplicate detection**: "this new thought looks 87% like a node you wrote in March" — for a permanent multi-year archive, this is memory the user doesn't have to carry.
- **Retrieval-scoped continuity checks**: check a scene against the *most relevant* prior scenes rather than a fixed window (§4).

## 3. GraphRAG-lite (no framework)

Heavy GraphRAG frameworks (Microsoft GraphRAG, LightRAG) spend most of their machinery on **LLM-based entity extraction to build a knowledge graph — which Quillnight doesn't need, because the Codex + `codex_relationships` + `codex_scene_links` already IS a curated knowledge graph.** The 2026 consensus for this situation: skip the framework, do graph-aware retrieval directly in SQL.

Context-assembly pipeline for any Enhance/continuity call:

```
1. SEED     Hybrid retrieval (RRF) → top-k relevant scenes/codex entries
2. RESOLVE  Map seed chunks to codex entities via codex_scene_links
3. EXPAND   1–2 hop traversal over codex_relationships (recursive CTE)
4. BOOST    Score each candidate: RRF score × hop-distance decay (1.0 / 0.5 / 0.25)
5. RESOLVE-TIME  Apply codex_arc_states point-in-time filtering (unchanged rule:
                 never leak later plot facts into an earlier scene's context)
6. PACK     Fill the token budget best-score-first; stable ordering (see §5)
```

This replaces the original flat "linked entries + one hop" rule with relevance-ranked, budget-aware assembly — same spirit, materially better context. (References: Stephen Collins' "Lightweight GraphRAG with SQLite" — this exact pattern; fast-graphrag's query-time Personalized-PageRank as a future refinement idea.)

## 4. Continuity Checker v2 — hybrid symbolic + neural

The original design sent everything to the LLM. Research (and common sense, once stated) splits the work: **facts the database already knows are checked by SQL; only genuinely semantic questions go to the model.**

### Tier 1 — Deterministic (SQL, zero LLM, zero hallucination, instant)
- **Early appearance**: character referenced in a scene ordered *before* their introduction point → a JOIN over `codex_scene_links` × `book_scene_order` × arc-state introduction markers. No model involved.
- **Timeline order conflicts**: outline order vs `in_story_time_sort_key` inversions not marked as intentional flashbacks — pure SQL.
- These produce `continuity_flags` rows with `source='deterministic'`, never wrong, never voted on.

### Tier 2 — Semantic (LLM, guarded)
For trait contradictions and subtle inconsistencies, using retrieval-scoped context (§2–3):

1. **Two-pass CoT**: Pass 1 lets the model reason in free prose ("analyze this scene against these facts; think step by step"). Pass 2 is a cheap extraction call converting that analysis to the JSON schema. Rationale: JSON-constrained decoding measurably degrades *reasoning* in small models ("Let Me Speak Freely," EMNLP 2024) while helping classification; dottxt's follow-up showed schema design is the difference — so the schema itself also puts `reasoning` and `evidence` fields **first** and `verdict`/`severity` **last** (answer-last forces the model to think before committing).
2. **Verbatim-quote guardrail (mechanical hallucination filter)**: every flag must include a `quote` field — the exact text it's flagging. The sidecar **string-matches the quote against the actual scene text; no match → flag silently dropped** before the user ever sees it. Citation-enforced prompting measurably reduces hallucination, and the string-match makes it deterministic rather than trusted.
3. **3-vote self-consistency**: run the Tier-2 pass 3× at temperature >0, union the flags (keyed by quote + type), **keep only flags appearing in ≥2 of 3 runs**. Nearly free in wall-clock terms because the shared prompt prefix is cached (§5) — only the decode repeats. (Self-consistency's gains have faded on frontier models but persist exactly where we live: small models, ambiguous tasks.) Ships in v1.1 once Phase 0 latency numbers confirm the budget; v1.0 runs single-pass with the quote guardrail.
4. Surviving flags persist with `source='ai'`, severity from the majority vote, rendered per the existing severity UI ([03-DATA-MODEL.md](03-DATA-MODEL.md)).

## 5. Prefix caching — local CAG for free

Ollama (via llama.cpp, `cache_prompt` defaults on) **reuses the KV cache when a request's token prefix is byte-identical to the previous request in that slot** — the cached prefix skips prompt processing entirely. On this hardware, a 4–8k-token codex context costs seconds per *uncached* call; cached, it's near-zero (reported time-to-first-token wins ≥65%). This is the "CAG" (cache-augmented generation) pattern, achieved with prompt discipline instead of new infrastructure:

**Rules (enforced in `prompt_builder.py`, stated once here):**
1. Prompt order everywhere: **[static system prompt] → [codex bible block] → [variable scene text] → [task instruction]**. Stable-most-first.
2. **Nothing volatile early in the prompt** — no timestamps, UUIDs, or request IDs before the variable section (one early differing token invalidates the whole cached prefix).
3. The codex bible block is serialized deterministically (stable entity ordering, stable field order) so unchanged codex = byte-identical block.
4. `OLLAMA_NUM_PARALLEL=1` — the cache is per-slot; parallel slots interleave and evict each other. A single-user app loses nothing.
5. `keep_alive` stays aligned with the existing keep-warm design ([04-LLM-INTEGRATION.md](04-LLM-INTEGRATION.md)) — model unload drops the cache.

This is why self-consistency voting (§4) and rapid sequential Enhance calls are affordable: the expensive prefill happens once per codex-state, not once per call.

## 6. External-verifier refine loop (the only loop that works at this scale)

Small models **cannot reliably critique themselves** (see §7). What works: loop against **deterministic external verifiers**:

- Enhance output → run **LanguageTool** + the phonetic spellcheck stack ([10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §4) over the *corrected* text → if the verifier still finds errors, one targeted re-prompt citing the specific findings → re-verify → present. Max one loop; never silent.
- Enhance output sanity gates (before the diff is even shown): length-ratio bounds and similarity thresholds auto-reject rewrites that drifted semantically (a known small-model failure is "answering" the text instead of correcting it); the prompt includes few-shot examples + "output only the corrected text."
- The Accept/Reject **span-level word diff** remains the last line of defense — research note: all current LLMs over-insert adverbs/adjectives when editing (>50% false-insertion rates in a 2026 eval), which is precisely why the diff UI was non-negotiable from day one.

## 7. Rejected patterns (recorded so they stay rejected)

| Pattern | Verdict | Why |
|---|---|---|
| **Unaided self-refine loops** (model critiques its own output) | ❌ Rejected | At 7B-class, unaided self-correction *degrades* output (ACL 2024, "Small LMs Need Strong Verifiers"); gains in the Self-Refine literature were GPT-4-class. External verifiers only (§6). |
| **Thinking-mode + JSON schema in one call** | ❌ Rejected | Broken/unreliable in Ollama/llama.cpp (ollama#10929: malformed JSON; llama.cpp#20345: grammar silently unenforced with thinking). Two-pass instead (§4). |
| **DeepSeek-R1 distills as the checker** | ❌ Rejected | Poor instruction/JSON adherence at 7–8B; qwen3.5 instruct is the better contradiction-checker and doubles for everything else. |
| **Heavyweight GraphRAG frameworks** | ❌ Rejected | Their main cost is LLM entity extraction we don't need — the Codex is already a curated graph (§3). |
| **Cross-encoder reranker (v1)** | ⏸ Deferred | Measurable gains exist (~5–15% NDCG@10) but it's ~568M params competing for 4GB VRAM, and Ollama has no first-class rerank endpoint. Revisit (CPU int8 ONNX over top-20) only if v1.1 retrieval quality disappoints. |
| **Microsoft-style whole-corpus community summarization** | ❌ Rejected | Wrong scale; wrong cost profile for a single-user local app. |
| **Bionic-Reading-style AI text decoration** | ❌ Rejected | See [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md) §3 — no evidence, and nothing decorates the manuscript. |

## Sources

Model landscape: [Ollama qwen3.5](https://ollama.com/library/qwen3.5), [Ollama gemma4](https://ollama.com/library/gemma4), [≤9B GEC study (arXiv 2505.06004)](https://arxiv.org/html/2505.06004v1), [GEC over-insertion eval (arXiv 2605.07635)](https://arxiv.org/html/2605.07635) · RAG stack: [sqlite-vec](https://github.com/asg017/sqlite-vec), [Mozilla Builders](https://builders.mozilla.org/project/sqlite-vec/), [qwen3-embedding](https://ollama.com/library/qwen3-embedding), [EmbeddingGemma](https://ai.google.dev/gemma/docs/embeddinggemma), [SQLite GraphRAG pattern](https://dev.to/stephenc222/how-to-build-lightweight-graphrag-with-sqlite-53le), [fast-graphrag](https://github.com/circlemind-ai/fast-graphrag), [FTS5+vector RRF](https://ceaksan.com/en/hybrid-search-fts5-vector-rrf) · Reasoning: ["Let Me Speak Freely" (arXiv 2408.02442)](https://arxiv.org/abs/2408.02442), [dottxt "Say What You Mean"](https://blog.dottxt.ai/say-what-you-mean.html), [self-consistency diminishing-returns study (arXiv 2511.00751)](https://arxiv.org/html/2511.00751), [Small LMs Need Strong Verifiers (ACL 2024)](https://aclanthology.org/2024.findings-acl.924.pdf) · Caching: [Ollama KV cache scheduling](https://jonathanding.github.io/llm-learning/en/articles/ollama-kv-cache-scheduling/), [CAG (arXiv 2412.15605)](https://arxiv.org/abs/2412.15605) · Bugs: [ollama#10929](https://github.com/ollama/ollama/issues/10929), [llama.cpp#20345](https://github.com/ggml-org/llama.cpp/issues/20345) · Guardrails: [Chain-of-Verification (arXiv 2309.11495)](https://arxiv.org/abs/2309.11495), [citation-enforced prompting (MDPI)](https://www.mdpi.com/2076-3417/16/6/3013)
