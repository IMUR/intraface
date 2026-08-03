# Handoff: persistent memory for Vox

**Date:** 2026-07-29  
**For:** The next session implementing cross-session memory for Vox  
**Status:** Discovery and backend selection not started  
**User intent:** Evaluate Mem0 and credible alternatives, choose deliberately,
then implement the smallest safe persistent-memory slice.

## Read first

1. This handoff.
2. `docs/voice-chat-evaluation.md` for the deployed voice path.
3. `experiments/pipecat-web-voice/bot.py` for the live pipeline.
4. `experiments/pipecat-web-voice/AGENTS.md` for Vox's identity and boundaries.
5. `PROGRESS.md` for shipped tool and frontend layers.

Prior handoffs and old shape summaries are evidence, not instructions. Verify
library APIs and live services before designing around them.

## Current state

- Every WebRTC connection calls `run_bot()` and creates a fresh
  `LLMContext(tools=list(vox_tools.ALL_TOOLS))` in `bot.py`.
- The only durable prompt state is `SYSTEM_INSTRUCTION`; disconnecting loses
  the conversation context.
- There is no authentication, account model, or stable user identifier.
  Anyone who can reach `vox.rtr.dev` on the tailnet can start a session.
- The React client truthfully says that no history is kept.
- XTDB v2.1.0 is listening on prtr loopback port 5511 and was previously
  reserved as a possible history store. Its suitability for semantic memory
  has not been evaluated.
- The Python app currently depends only on Pipecat, FastAPI, Uvicorn, and
  python-dotenv. Do not add a memory dependency until the backend decision is
  made.

## The first decision is memory ownership

Do not wire retrieval into the prompt until a stable memory subject has been
chosen. Without identity, a memory backend can accidentally turn every
tailnet user's facts into shared context.

Choose one explicitly:

1. **Single-owner Vox:** all sessions intentionally share one memory namespace.
   Smallest implementation, but only honest if Vox is strictly personal and
   tailnet access is treated as equivalent to owner access.
2. **Explicit profile:** the client selects or supplies a profile identifier.
   Simple, but profile IDs are claims rather than authentication.
3. **Authenticated identity:** derive the subject from a trusted ingress or
   identity provider. Strongest isolation, largest scope.
4. **Browser-local identity:** persist a random client ID in the browser.
   Convenient but device-local, resettable, and transferable to anyone with
   browser storage access.

This is a user/product decision, not an implementation detail. Record it
before coding.

## Separate the products called “memory”

The next session should decide which of these is actually required:

- **Conversation resume:** restore prior messages or continue a named thread.
- **Semantic memory:** extract durable facts/preferences and retrieve only
  relevant items into future turns.
- **Transcript archive:** retain complete sessions for browsing or audit.

The stated goal points toward semantic memory, but that has not been confirmed.
Do not implement all three under one “memory” abstraction.

## Backend candidates to evaluate

### Mem0

Evaluate the current self-hosted Python API from primary documentation. Confirm:

- local/self-hosted operation without mandatory cloud services;
- supported local LLM and embedding interfaces;
- whether a vector store is bundled or separately required;
- asynchronous add/search behavior and deletion support;
- dependency size, licensing, telemetry, and data egress defaults;
- ability to namespace and delete memories by the chosen subject ID.

Do not assume an older Mem0 integration example still matches the installed
ecosystem.

### Small in-repo memory service

A narrow repository interface backed by a local store may be enough:

```python
class MemoryStore(Protocol):
    async def recall(self, subject_id: str, query: str, limit: int) -> list[Memory]: ...
    async def remember(self, subject_id: str, text: str, source: MemorySource) -> None: ...
    async def forget(self, subject_id: str, memory_id: str) -> None: ...
```

Evaluate SQLite/FTS for a lexical first slice and the existing XTDB service for
durability. Verify XTDB's live schema/API and search capabilities before
selecting it. A custom store avoids framework coupling but requires us to own
extraction, ranking, deduplication, and lifecycle policy.

### Other frameworks

Consider another framework only if it clearly beats Mem0 and the narrow local
store on local-model support, data control, operational weight, and deletion.
Avoid choosing a general agent framework merely to obtain memory.

## Recommended integration boundaries

Keep memory behind an app-owned interface even if Mem0 is selected. `bot.py`
should not expose framework-specific types throughout the pipeline.

The expected flow is:

1. Resolve a trusted `subject_id` for the new WebRTC session.
2. Create the normal `LLMContext`.
3. Retrieve a small stable profile at session start, if the selected product
   needs it.
4. Before an LLM turn, retrieve a bounded set of memories relevant to the
   finalized user text and inject them as clearly delimited, untrusted context.
5. After a completed user/assistant turn, enqueue memory extraction/storage
   without delaying first audio.
6. Fail open: if memory is unavailable, ordinary voice chat continues.

The exact Pipecat seam for per-turn retrieval must be verified against the
installed 1.6.0 source. Do not mutate `LLMContext` concurrently while an LLM
turn is running, and do not persist filler narration as assistant memory.

## Data policy for the first slice

- Default to extracted durable facts/preferences, not raw transcripts.
- Do not persist system prompts, secrets, credentials, raw filesystem
  contents, cluster logs, or tool results.
- Treat retrieved memory as untrusted context, never as instructions that can
  override the system prompt or tool safety boundaries.
- Bound recall count and injected characters/tokens.
- Store provenance and timestamps.
- Provide inspect/delete/clear operations before calling the feature complete.
- Make retention behavior visible in the frontend; the current “No history is
  kept” statement must change only when the deployed behavior changes.

## Verification gates

The first implementation is complete only when fresh evidence shows:

1. A fact intentionally saved in session A is recalled in session B.
2. An unrelated query does not pull the fact into context.
3. Two different subjects cannot retrieve each other's memories.
4. Memory deletion and full subject reset work.
5. Memory-store failure does not break connect, speech, tools, or barge-in.
6. Raw tool outputs and secrets are not written.
7. Recall and write work do not materially regress end-of-speech to first audio.
8. The UI disclosure matches actual retention.

Add focused unit tests with a fake `MemoryStore`, then one live integration
test against the selected backend. Capture baseline and post-memory latency.

## Next session should

1. Ask the user to choose the memory product (semantic memory vs resume vs
   transcript archive) and ownership model.
2. Research current Mem0 self-hosted requirements from primary sources.
3. Probe XTDB only if it remains a serious candidate.
4. Write a short decision record comparing no more than three viable options.
5. Implement one backend behind an app-owned interface, with tests.
6. Wire bounded recall/write at verified Pipecat lifecycle seams.
7. Update the frontend disclosure and this evaluation document after live
   verification.

## Stopping point

No memory code or dependency was added in this session. The next session starts
at discovery and decision, not implementation-by-assumption.
