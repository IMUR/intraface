# vox capability stack — progress

Tracks the build-out of vox's tool/identity capabilities across five
layers. Source of truth for what's done, what's in progress, and what's
blocked. Companion to `experiments/pipecat-web-voice/AGENTS.md` (design)
and `docs/handoffs/2026-07-29-vox-agent-capabilities.md` (original scope).

**Last updated:** 2026-07-29 (Layer 3 web search shipped)

---

## Layer 0 — Identity / self-knowledge

Status: **shipped** (2026-07-29)

- [x] `AGENTS.md` authored at `experiments/pipecat-web-voice/AGENTS.md`
- [x] System prompt rewritten to enforce tool-first behavior on cluster queries
- [x] Self-knowledge of tools and refusal boundaries
- [x] Model self-knowledge — system prompt now names Qwen3.6 + port + speech path (shipped 2026-07-29 after Layer 2)
- [ ] Voice-UX observations tracked (model misreads short phrases; brevity vs detail tension; Layer 2 path-arg imprecision; soft-refusal miss on edit requests)

## Layer 1 — Read-only cluster ops

Status: **shipped** (2026-07-29)

- [x] `_ssh()` helper with stale-ControlMaster retry and trtr timeout
- [x] `check_node(node)` — uptime + load + per-node service probes
- [x] `list_services(node)` — systemd units matching cluster patterns
- [x] `get_log_tail(node, service, lines)` — bounded journalctl tail
- [x] `get_port_state(node)` — filtered listeners in cluster port blocks
- [x] Filler narration hook (`_tool_filler`) with per-tool spoken fillers
- [x] `max_completion_tokens` raised 120 → 300 for tool-using turns
- [x] Live-cluster test suite (`tests/test_tools.py`) — all checks pass
- [x] End-to-end LLM probe — correct tool selection on all test queries
- [x] Restarted bot process with new code

## Layer 2 — Filesystem awareness (read-only)

Status: **shipped** (2026-07-29)

- [x] Path allowlist (`_ALLOWED_ROOTS`) — `~/prj/intraface/` + reserved slots
- [x] `_resolve_and_check` helper — realpath + prefix check, blocks `..` and symlinks
- [x] `read_file(path)` — 4 KiB cap, returns `truncated` flag
- [x] `list_directory(path)` — 50-entry cap, name + type + size
- [x] `find_files(pattern, root)` — `rg --files`, 50-result cap
- [x] `grep_files(pattern, root)` — ripgrep, 20-match cap with line numbers
- [x] `_local` helper using `create_subprocess_exec` (argv form, no shell)
- [x] 11 Layer 2 checks added to `tests/test_tools.py` — all pass
- [x] Wired into `bot.py` with Layer 2 filler entries
- [x] System prompt updated to mention filesystem tools and refusal
- [x] End-to-end LLM probe — correct tool selection on all 5 Layer 2 test queries
- [x] Restarted bot process with Layer 2 code

### Layer 2 voice-UX observations (tracked, not fixed)

- Path argument imprecision — model often guesses `~/prj/intraface/bot.py`
  instead of `~/prj/intraface/experiments/pipecat-web-voice/bot.py`. Allowlist
  accepts, `isfile` rejects, costs an extra round-trip.
- Soft refusal miss — "edit bot.py" got a `read_file` call rather than an
  upfront refusal. No security boundary crossed (read-only), but the model
  interpreted intent as planning rather than refusal.

## Layer 3 — Web search

Status: **shipped** (2026-07-29)

- [x] `web_search(query, intent)` against `sch.rtr.dev` SearXNG
- [x] Intent enum mapping: general / code / docs / research / ml
- [x] Result shaping — top 3 results with title, domain, URL, and capped snippet
- [x] Six Layer 3 checks added; complete tool suite passes
- [x] Wired into `bot.py` with query-specific filler
- [x] System prompt requires web search for current docs, versions, papers,
      packages, and other facts likely stale in model training
- [x] End-to-end LLM probe selected correct intents for general, docs, and
      research queries; Layer 1/2 regression queries still selected correctly
- [x] Bot restarted with Layer 3 code (PID 1346362)
- [ ] `fetch_page(url)` deferred — needs "summarize this" pattern proven first

## Layer 4 — Pi delegation

Status: **planned** (not started)

- [ ] `delegate_to_pi(task)` running `pi --print --no-tools`
- [ ] Per-session `--session-id` (one Pi session per WebRTC connection)
- [ ] Length cap on Pi output (~500 chars) before LLM sees it
- [ ] Tests added
- [ ] Wired into `bot.py` with filler entry
- [ ] Stronger `--no-tools` scope verification (try invoking a tool by name)

## Layer 5 — Modes (tool subsets per session)

Status: **planned** (not started)

- [ ] Mode taxonomy — minimal / cluster / extended / research / delegate
- [ ] URL-derived mode selection (`vox.rtr.dev/?mode=cluster`)
- [ ] Default mode = conversational-only (today's behavior)
- [ ] Voice-activated switching explicitly excluded

## Cross-cutting

- [x] `engines.toml [defects.ik_llama_json_schema]` stamped resolved with verification
- [x] Handoff's fabricated Pattern 1/2 (`FunctionCallParams`/`register_function`)
      replaced with verified patterns and originals retained for provenance
- [x] Evaluation doc's schema-defect section and bot.py shape notes stamped
- [ ] Systemd unit for bot process — survives reboots (separate workstream,
      tracked in `docs/voice-chat-evaluation.md` follow-up #3)

## Frontend swap (2026-07-29)

- [x] React app (`frontend/dist/`) served as live page at `/`
- [x] Vanilla JS client (`frontend/vanilla/`) preserved at `/vanilla/` as fallback
- [x] `/assets/*` mounted for hashed React build assets
- [x] `/static/*` retained for legacy callers
- [x] `server.py` rewritten with new routes — all four static paths serving
- [x] Restarted bot process (PID 1332091), both pages reachable end-to-end
- [x] **Verified working live** — user tested vox.rtr.dev end-to-end at 13:24.
      Bot log shows full LLM+TTS round trip ("Vox here, ready to help."),
      clean pipeline teardown. React UI is the live page.

### RTVI handoff was wrong about the prerequisite

The frontend handoff (`docs/handoffs/2026-07-30-vox-rtvi-backend.md`)
said the React client would hang until RTVI was added to `bot.py`.
Investigation showed RTVI was already active by default (pipecat-ai 1.6.0's
`PipelineWorker.__init__` has `enable_rtvi=True`, auto-creating the
processor and observer). The handoff's recommended API (`RTVIConfig`)
does not exist in 1.6.0. The handoff is stamped stale at the top with
the correction; original retained for provenance.

The swap landed cleanly with no `bot.py` change. The vanilla client at
`/vanilla/` remains as fallback using the raw `{"role","text"}` protocol
via `TranscriptForwarder` (kept in place per the handoff's backward-compat
note).

## Notes

- Voice-UX observations from 2026-07-29 live test:
  - Tools fire correctly end-to-end (check_node, get_port_state verified live)
  - Filler narration works ("checking drtr", "checking listeners on crtr")
  - Barge-in interrupts cleanly
  - Two UX observations tracked but not fixed (see Layer 0 checklist):
    1. Model misread "that's enough" as permission to proceed (interpretation issue)
    2. "Be brief" prompt conflicts with explicit "lengthy story" request
