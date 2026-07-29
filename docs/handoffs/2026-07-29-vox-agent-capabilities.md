# Handoff: vox agent capability management

**Date:** 2026-07-29
**For:** Engineer picking up agent capability work on the vox voice bot
**Scope:** Giving the voice bot tools, identity, and self-awareness beyond pure conversation

---

## Current state — what's deployed

The voice bot at `experiments/pipecat-web-voice/bot.py` is purely conversational. No tools, no identity beyond a one-line system prompt, no awareness of the cluster it runs on.

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

Pipecat's `OpenAILLMService` natively supports OpenAI-format function calling. The llama-server backend also supports it (with the caveat below). Two registration patterns per [pipecat docs](https://docs.pipecat.ai/pipecat/learn/function-calling):

### Pattern 1 — Direct function (recommended for v1)

```python
from pipecat.services.llm_service import FunctionCallParams

async def check_node(params: FunctionCallParams, node: str):
    """Check if a cluster node is reachable and report basic status.
    Args:
        node: Cluster node name (prtr, drtr, crtr, or trtr)
    """
    result = await _ssh(node, "uptime; systemctl is-active cockpit 2>/dev/null")
    await params.result_callback({"status": result})

context = LLMContext(tools=[check_node])
```

Pipecat auto-derives the JSON Schema from the type annotations + docstring. No manual schema work needed.

### Pattern 2 — FunctionSchema (use only if you need enums or strict constraints)

```python
from pipecat.services.llm_service import FunctionSchema

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
    handler=check_node_handler,
)
```

### Voice-specific hooks

Pipecat emits events for function call lifecycle. Hook these to keep the user informed during tool execution:

```python
@llm.event_handler("on_function_calls_started")
async def on_function_calls_started(service, function_calls):
    # Push filler speech so the user isn't in silence during the SSH call
    from pipecat.frames.frames import TTSSpeakFrame
    await tts.queue_frame(TTSSpeakFrame("Let me check that.""))

@llm.event_handler("on_function_calls_cancelled")
async def on_function_calls_cancelled(service, function_calls):
    # Handle barge-in during tool execution
    for item in function_calls:
        logger.info(f"Function call cancelled: {item.function_name}")
```

For long-running tools that should survive interruption: `OpenAILLMService(..., enable_async_tool_cancellation=True)` + `@tool_options(cancel_on_interruption=False)` on the function.

---

## Critical llama-server constraint — function calling has a known defect

**The resident llama-server (`ik_llama.cpp` pinned commit `86d8e9a1`, 2026-07-06) has a known JSON Schema parsing bug.** When the OpenAI SDK sends a tool definition that includes a schema value of `true` (allowed in JSON Schema 2020-12, means "accept any value"), ik_llama.cpp rejects it with:

```
Error: 500: {"code":500,"message":"Unable to generate parser for this template. Automatic parser generation failed: JSON schema conversion failed:\nUnrecognized schema: true","type":"server_error"}
```

This is documented in `engines.toml [defects.json_schema]` and reproducible from Pi.

**Impact on agent capability work:** Some tool schemas generated by pipecat or by the OpenAI SDK may include `true` values (especially `additionalProperties: true` on object types). If you see this 500 error when registering tools, it's this defect, not your schema.

**Status as of 2026-07-29:** A one-line fix exists upstream (add boolean handling to `common/json-schema-to-grammar.cpp` before the existing `{}` case). The user is handling that fix in a separate workstream. Until it lands, you may need to write schemas by hand (avoiding `true`/`false` literal values) rather than relying on pipecat's auto-derivation.

**Verification step before building tools:** Test a single tool registration against the live llama-server. If it returns 500, the schema-derivation path is blocked until the upstream fix lands.

---

## SSH execution path

The bot runs on prtr as user `prtr`. The cluster SSH config (`~/.ssh/config`) provides passwordless aliases:

| Alias | Resolves to | User |
|---|---|---|
| `c` / `crtr` | `100.64.0.4` / `192.168.254.11` | `crtr` |
| `p` / `prtr` | `100.64.0.2` / `192.168.254.22` | `prtr` |
| `d` / `drtr` | `100.64.0.3` / `192.168.254.33` | `drtr` |
| `t` / `trtr` | `100.64.0.1` / `192.168.254.107` | `trtr` |

For tool execution, use `asyncio.create_subprocess_exec("ssh", "<alias>", "<command>")` — never `shell=True`, never `sh -c`. The cluster's `ControlMaster auto` SSH config (per `rtr-profile.md:211`) multiplexes connections so repeated SSH calls are fast (~10ms after first connection).

**Cluster SSH discipline** (from `rtr-profile.md:283-294`):
- Bash is the default login shell on Linux nodes. `ssh <node> '<cmd>'` works directly.
- Don't use `zsh -l -c` for non-interactive ops — unreliable pattern, unnecessary on Linux nodes.
- `ControlMaster` sockets can stale after node reboot. If SSH fails with "Connection closed", run `ssh -O exit <node>` then retry.

---

## Identity / AGENTS.md scope

Author at `experiments/pipecat-web-voice/AGENTS.md`. Should cover:

1. **What vox is** — voice interface to the rtr cluster, browser-accessible at vox.rtr.dev, talks through WebRTC, uses the resident Qwen3.6 Core
2. **What vox is not** — not Pi, not a coding agent, not a substitute for shell access, not a general-purpose chatbot
3. **What vox knows** — cluster topology (load from `rtr-profile.md` facts: 4 nodes, port blocks, services, model identities)
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

## What to read first (in order)

1. `experiments/pipecat-web-voice/bot.py` — current pipeline structure
2. `experiments/pipecat-web-voice/README.md` — deployment context
3. `rtr-profile.md` lines 12-18 (nodes) and 80-148 (port blocks) — what the tools will inspect
4. `engines.toml [defects.json_schema]` — the schema parsing bug to watch for
5. `docs/charter.md` — conceptual model (not directly applicable but informs identity choices)
6. [Pipecat function calling docs](https://docs.pipecat.ai/pipecat/learn/function-calling) — canonical API reference

---

## Open questions for the user before starting

1. **What cluster services should the bot know about by name?** rtr-profile.md lists many; some are inactive. The bot's mental model should match what's actually deployed.

2. **Should the bot know about the charter / five tests?** Probably not directly — too abstract for voice — but it should know it's part of a system with disciplines, not just a chatbot.

3. **What's the failure mode for unreachable nodes?** Currently `ssh trtr` might hang or fail (macOS sleeps). Tools should have a short timeout (3-5s) and return a clean "unreachable" result, not raise.

4. **Is the `~/.pi/agent/AGENTS.md` web search recipe worth porting?** Pi has a SearXNG endpoint at `sch.rtr.dev`. If the bot should be able to look things up, that's a useful read-only tool — but it's outside the v1 scope you set.
