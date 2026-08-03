# Handoff: vox agent capability management

**Date:** 2026-07-29
**For:** Engineer picking up agent capability work on the vox voice bot
**Scope:** Giving the voice bot tools, identity, and self-awareness beyond pure conversation

**Your companion file:** `docs/voice-chat-evaluation.md`. That's the only
other file you should need. Its **"Reference: shared context"** section has
the current `bot.py` shape (pipeline order, system prompt, env vars),
`server.py` shape, `static/index.html` shape, full cluster topology (nodes,
SSH aliases, port blocks), SSH execution discipline, the JSON schema defect
details, ADRs in force, and where every file lives. Read its Reference
section before starting.

If something you need isn't in either this handoff or the evaluation doc's
Reference section, surface it as a gap before guessing.

---

## Addendum 2026-07-29 (post-implementation) — read this first

The original scope below (v1: read-only cluster ops) has been **implemented
and verified live**. Files now in place:

- `experiments/pipecat-web-voice/AGENTS.md` — vox identity, full target state
- `experiments/pipecat-web-voice/tools.py` — `_ssh()` helper + four read-only
  tools (`check_node`, `list_services`, `get_log_tail`, `get_port_state`)
- `experiments/pipecat-web-voice/bot.py` — tools registered via
  `LLMContext(tools=[...])`, filler narration hook wired,
  `max_completion_tokens` raised from 120 to 300 for tool-using turns
- `experiments/pipecat-web-voice/tests/test_tools.py` — live-cluster tests
  (passes 100% as of 2026-07-29)

End-to-end verification: live llama-server correctly selects tools for
voice-shaped queries ("is drtr up?" → `check_node`, "what's listening on
prtr?" → `get_port_state`, etc.) and declines to call tools for non-cluster
questions. See test logs in commit history.

**Current status:** Layers 0–4 are implemented. This includes allowlisted
filesystem tools, SearXNG web search, strict model-visible enums for constrained
arguments, and per-WebRTC-session Pi delegation with all Pi tools disabled.
Layer 5 modes remains planned. See `experiments/pipecat-web-voice/AGENTS.md`
and the root `PROGRESS.md` for the live capability inventory.

### Corrections to the original handoff (below)

The original Patterns 1 and 2 in the next section reference APIs that do
**not** exist in pipecat 1.6.0:

- `from pipecat.services.llm_service import FunctionCallParams` — wrong path.
  Real path: `from pipecat.services.llm_service import FunctionCallParams`
  (the symbol exists, the import path in the original Pattern 1 source
  snippet was correct, but Pattern 2's `from pipecat.services.llm_service
  import FunctionSchema` is **wrong** — that class is not there).
- A classic `register_function` API exists in pipecat 1.6.0, but it is not
  needed here. Direct functions and handler-carrying `FunctionSchema` objects
  register automatically when passed to `LLMContext(tools=...)`.
- The schema-defect section below is **resolved** as of 2026-07-29. See
  `engines.toml [defects.ik_llama_json_schema]` for verification details.

The corrected, verified patterns are in the next section, marked **(verified
2026-07-29)**. The original (incorrect) text is retained below them for
provenance.

---

## Current state — what's deployed

The voice bot at `experiments/pipecat-web-voice/bot.py` has a durable
`system_instruction` and Layers 1–4 registered: read-only cluster inspection,
allowlisted filesystem reads, web search, and tool-disabled Pi delegation.

**Working today:**
- WebRTC voice chat via pipecat SmallWebRTCTransport
- STT (Parakeet on drtr:7733) → LLM (Qwen3.6 on prtr:7712) → TTS (Chatterbox on drtr:7744, streaming)
- Live transcript forwarded to browser via WebRTC data channel
- Barge-in (full-duplex interruption) works, ~10ms cutoff latency
- TTS streaming (deployed 2026-07-29) cut first-audio latency from 22s to ~2s on long responses

**Architecture:**
```
Browser  ──HTTPS──►  crtr Caddy  ──►  prtr:7878 (bot)
                                        ├──► 127.0.0.1:7712  llama-server
                                        ├──► 100.64.0.3:7733 Parakeet STT
                                        └──► 100.64.0.3:7744 Chatterbox TTS
```

The bot runs on prtr as user `prtr`. SSH aliases to other cluster nodes (`drtr`, `crtr`, `trtr`) are configured and passwordless.

---

## Confirmed scope (decided 2026-07-29)

**Identity source:** Author a new `AGENTS.md` for vox — purpose-built for the voice bot. Lives at `experiments/pipecat-web-voice/AGENTS.md`. Don't reuse Pi's identity (Pi has tools/access the voice bot doesn't have and shouldn't pretend to).

**Tool scope (v1):** Read-only cluster ops only. No mutation, no destructive commands, no shell execution that could change state. Specifically:
- `check_node(node)` — uptime + key service status
- `list_services(node)` — active systemd units matching cluster patterns
- `get_log_tail(node, service, lines)` — `journalctl -u <service> -n <lines>`
- `get_port_state(node)` — `ss -tlnp` filtered to cluster port blocks

**Explicitly deferred:** knowledge lookup (doc/codebase search), shell execution with mutation, cluster control (start/stop services). Add only when read-only tools are stable and patterns recur.

---

## Pipecat function calling — verified working

Pipecat's `OpenAILLMService` natively supports OpenAI-format function calling. The llama-server backend also supports it (with the caveat below).

### Patterns that actually work in pipecat 1.6.0 (verified 2026-07-29)

There is one canonical path: pass async functions (or `FunctionSchema`
objects) directly to `LLMContext(tools=[...])`. The function's first
parameter must be named `params` and typed as `FunctionCallParams`;
pipecat's `DirectFunctionWrapper` reads the rest of the signature and the
docstring to auto-derive the JSON Schema sent to the model. Handlers are
registered automatically, so this implementation does not need a separate
`register_function` call.

**Direct function (recommended — what `tools.py` uses):**

```python
from pipecat.services.llm_service import FunctionCallParams

async def check_node(params: FunctionCallParams, node: str) -> None:
    """Check if a cluster node is reachable and report basic status.
    Args:
        node: Cluster node name (prtr, drtr, crtr, or trtr)
    """
    result = await _ssh(node, "uptime; ...")
    await params.result_callback({"node": node, "reachable": True, ...})

# bot.py:
context = LLMContext(tools=[check_node, list_services, ...])
```

The docstring's `Args:` block is what populates the per-parameter
description in the derived schema. Type annotations become the JSON Schema
type. Enums are not supported via this path — for those use `FunctionSchema`.

**Explicit FunctionSchema (when you need enums or strict constraints):**

```python
from pipecat.adapters.schemas.function_schema import FunctionSchema

check_node_schema = FunctionSchema(
    name="check_node",
    description="Check if a cluster node is reachable",
    properties={
        "node": {
            "type": "string",
            "enum": ["prtr", "drtr", "crtr", "trtr"],
            "description": "Cluster node name",
        }
    },
    required=["node"],
    handler=check_node_handler,  # async (params, node) -> None
)
# Then: LLMContext(tools=[check_node_schema])
```

Note the import path: `pipecat.adapters.schemas.function_schema`, **not**
`pipecat.services.llm_service`. The latter was a fabrication in the
original handoff (see addendum at top).

`FunctionSchema.to_default_dict()` emits exactly `{type, properties,
required}` — no `additionalProperties: true`. Verified by direct
inspection in `tools.py`'s tests. This means the historical llama-server
schema defect (below) cannot be triggered via the standard path, even on
an unfixed server.

### Voice-specific hooks (verified)

Pipecat emits events for function call lifecycle. Hook these to keep the
user informed during tool execution. The `bot.py` implementation uses
exactly this shape:

```python
@llm.event_handler("on_function_calls_started")
async def on_function_calls_started(service, function_calls):
    # Push filler speech so the user isn't in silence during the SSH call.
    # Specific beats generic — see bot.py's _tool_filler() helper which
    # derives "checking drtr" from check_node(node="drtr").
    from pipecat.frames.frames import TTSSpeakFrame
    await tts.queue_frame(TTSSpeakFrame("Let me check that."))

@llm.event_handler("on_function_calls_cancelled")
async def on_function_calls_cancelled(service, function_calls):
    # Handle barge-in during tool execution
    for item in function_calls:
        logger.info(f"Function call cancelled: {item.function_name}")
```

For long-running tools that should survive interruption, the 1.6.0
mechanism is the `@tool_options(cancel_on_interruption=False)` decorator
on the function itself (not an `OpenAILLMService` init kwarg as the
original handoff claimed).

### Original patterns (retained for provenance — DO NOT USE)

The two patterns below appeared in the original handoff. One used obsolete
separate-registration guidance and the other used an invalid import. They are
kept so future readers can see what was wrong. Use the verified patterns above.

<details>
<summary>Original Pattern 1 (obsolete separate-registration guidance)</summary>

```python
# `LLMContext(tools=[check_node])` is sufficient. Do not add a redundant
# classic `register_function` step for this direct function.
from pipecat.services.llm_service import FunctionCallParams  # this import is OK

async def check_node(params: FunctionCallParams, node: str):
    result = await _ssh(node, "uptime; systemctl is-active cockpit 2>/dev/null")
    await params.result_callback({"status": result})

context = LLMContext(tools=[check_node])  # this line is correct
```

</details>

<details>
<summary>Original Pattern 2 (fabricated import — does not work)</summary>

```python
# BROKEN: FunctionSchema is not in pipecat.services.llm_service.
# BROKEN: real path is pipecat.adapters.schemas.function_schema.
from pipecat.services.llm_service import FunctionSchema  # WRONG

check_node_schema = FunctionSchema(
    name="check_node",
    description="Check if a cluster node is reachable",
    properties={"node": {"type": "string", "enum": [...], "description": "..."}},
    required=["node"],
    handler=check_node_handler,
)
```

</details>

---

## Critical llama-server constraint — function calling has a known defect

> **STATUS (2026-07-29): RESOLVED.** Verified live — see `engines.toml
> [defects.ik_llama_json_schema]` for verification details. The section
> below is retained for provenance; do not act on it without re-verifying
> the defect is back.

**The resident llama-server has a JSON Schema parsing bug** that affects tool registration. Full background (symptom, root cause, fix status, engines.toml reference) is in the evaluation doc's Reference section under "llama-server JSON schema defect."

**Impact on agent capability work:** Some tool schemas generated by pipecat or by the OpenAI SDK may include `true` values (especially `additionalProperties: true` on object types). If you see this 500 error when registering tools, it's this defect, not your schema.

**Status as of 2026-07-29:** A one-line fix exists upstream. The user is handling that fix in a separate workstream (Pi's terminal on prtr has the latest state). Until it lands, you may need to write schemas by hand with `FunctionSchema` (avoiding `true`/`false` literal values) rather than relying on pipecat's auto-derivation from direct functions.

**Verification step before building tools:** Test a single tool registration against the live llama-server (`http://127.0.0.1:7712/v1`). If it returns 500, the schema-derivation path is blocked until the upstream fix lands — stop and surface this rather than working around it silently.

> **Update 2026-07-29:** The verification step above was performed and passed.
> All three probe schemas (with `additionalProperties: true`, minimal,
> typed-enum) returned HTTP 200, and a full tool-call roundtrip succeeded.
> The defect is empirically gone against the pinned commit. Mechanism
> unclear — see engines.toml.

---

## SSH execution path

The bot runs on prtr as user `prtr`. The cluster SSH config provides
passwordless aliases (table in evaluation doc's Reference section). For tool
execution, `tools.py:_ssh()` uses
`asyncio.create_subprocess_exec("ssh", node, command)` where `command` is a
single shell string sent to the remote login shell.

**Why shell string, not argv array:** several tools need shell features
(pipes for `systemctl | grep`, command substitution for `$(...)`). These
don't survive `shlex.split` followed by exec. Safety rests on the command
being constructed from fixed shapes inside `tools.py` — the model only
supplies arguments that go through `shlex.quote()` or strict regex
validation before reaching the SSH boundary. No caller interpolates raw
user/LLM strings without quoting. **Never `shell=True`** (different
process, more dangerous, and unnecessary here — the remote login shell
handles the command string).

**Cluster SSH discipline** (full version in evaluation doc's Reference
section under "SSH execution discipline"). Key points:
- Bash is the default login shell on Linux nodes — bare `ssh <node> '<cmd>'` works
- Don't use `zsh -l -c` for non-interactive ops
- `ControlMaster` sockets can stale after node reboot — `ssh -O exit <node>` then retry
- trtr is macOS and may sleep — tools targeting trtr should use 3-5s timeout and return "unreachable" rather than raise

---

## Identity / AGENTS.md scope

Author at `experiments/pipecat-web-voice/AGENTS.md`. Should cover:

1. **What vox is** — voice interface to the rtr cluster, browser-accessible at vox.rtr.dev, talks through WebRTC, uses the resident Qwen3.6 Core
2. **What vox is not** — not Pi, not a coding agent, not a substitute for shell access, not a general-purpose chatbot
3. **What vox knows** — cluster topology (4 nodes, port blocks, services, model identities — all in the evaluation doc's Reference section)
4. **What vox can do** — answer questions about cluster state via the registered tools
5. **What vox should refuse** — mutation, destructive commands, actions outside its tool set, pretending to have capabilities it doesn't
6. **Voice constraints** — short sentences, plain spoken language, narrate during tool calls, summarize tool results in one sentence (don't read raw output)

**Pattern reference** (do not copy): `~/.pi/agent/AGENTS.md`. Pi's identity includes web search recipes and extension references that don't apply to vox.

---

## Tool result shaping for voice

Tool results need to be voice-friendly. A `journalctl` tail of 50 lines is unreadable as speech. Three principles:

1. **Return short text** (target 50-100 words max per tool result)
2. **Structure as data, not log output** — `{"status": "active", "uptime": "3 days", "load": "0.10"}`
3. **System prompt instructs summarization** — bot speaks a one-sentence summary, not the raw result

Example tool result:
```json
{"node": "drtr", "reachable": true, "uptime": "11 days", "load": "0.10", "services": {"parakeet-stt": "active", "chatterbox-tts": "active"}}
```

Bot speaks: *"drtr has been up for 11 days with light load. Parakeet and Chatterbox are both running."*

---

## Implementation order (recommended)

1. **Verify tool calling works at all** — register one trivial tool (e.g., `get_current_time()`), confirm llama-server accepts the schema. If it 500s, the schema defect is blocking — stop and coordinate with the user.
2. **Author `AGENTS.md`** — identity first, tools later. Get the bot's self-conception stable before adding capabilities.
3. **Implement `tools.py`** with the four read-only functions, each tested independently via direct call before registering with the LLM.
4. **Wire into `bot.py`** — import tools, pass to `LLMContext`, add `on_function_calls_started` filler hook.
5. **Test end-to-end** via `https://vox.rtr.dev/`: "is drtr up?", "what services are running on prtr?", "tail the last 10 lines of the parakeet log on drtr".
6. **Iterate on system prompt** — voice UX for tool-using agents is hard. The bot will tend to either over-explain or under-explain tool results. Expect prompt tuning.

---

## Files you'll touch

```
experiments/pipecat-web-voice/
├── AGENTS.md              ← new (identity)
├── tools.py               ← new (async tool functions)
├── bot.py                 ← modify (import tools, register, add filler hook)
└── tests/
    └── test_tools.py      ← new (test tool functions in isolation)
```

Don't need to touch: `server.py`, `static/index.html`, anything in `docs/decisions/`.

---

## What to read first

1. **Evaluation doc's Reference section** — for the current bot.py shape, cluster topology, SSH discipline, schema defect, file locations, ADRs in force. This is your primary source of facts.
2. **This handoff's "Confirmed scope" section above** — for what was decided (identity source, tool whitelist).
3. **`experiments/pipecat-web-voice/bot.py`** — read directly when you're ready to modify it. The Reference section summarizes its shape; the actual file is the truth.
4. [Pipecat function calling docs](https://docs.pipecat.ai/pipecat/learn/function-calling) — canonical API reference for `FunctionCallParams`, `FunctionSchema`, `register_function`.

Optionally, if you want deeper context (not required to start):
- `docs/charter.md` — conceptual model; informs identity choices but not directly applicable
- `docs/decisions/0001-core-unit-model-custody.md` and `0007-explicit-per-node-runtime-deployment.md` — architectural constraints already summarized in Reference
- `~/.pi/agent/AGENTS.md` — Pi's identity, for pattern reference only (do not copy)

---

## Open questions for the user before starting

1. **What cluster services should the bot know about by name?** The evaluation doc's Reference section lists the voice-relevant live ports (7878, 7712, 7733, 7744, 5511, 443) but the broader cluster has more services, some inactive. The bot's mental model should match what's actually deployed — ask the user to enumerate beyond what's in the Reference section if needed.

2. **Should the bot know about the charter / five tests?** Probably not directly — too abstract for voice — but it should know it's part of a system with disciplines, not just a chatbot.

3. **What's the failure mode for unreachable nodes?** Currently `ssh trtr` might hang or fail (macOS sleeps). Tools should have a short timeout (3-5s) and return a clean "unreachable" result, not raise.

4. **Is the `~/.pi/agent/AGENTS.md` web search recipe worth porting?** Pi has a SearXNG endpoint at `sch.rtr.dev`. If the bot should be able to look things up, that's a useful read-only tool — but it's outside the v1 scope you set.
