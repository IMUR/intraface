# vox-lifecycle extension — integration notes

## What was created

```
experiments/pipecat-web-voice/extensions/
  vox-lifecycle.ts          # Production extension (87 lines, ~3.4 KB)
experiments/pipecat-web-voice/tests/
  test_vox_lifecycle.py     # Comprehensive test suite (15 test groups, all pass)
```

## Findings

### 1. `--no-extensions` + `--extension <path>` is explicitly supported

Pi's help text states: `--no-extensions, -ne  Disable extension discovery (explicit -e paths still work)`. Verified live: `--no-extensions` prevents loading anything from `~/.pi/agent/extensions/` or `.pi/extensions/`, but an explicit `--extension /path/to/file.ts` loads regardless. This is the correct mechanism for project-owned extensions without exposing global extensions.

### 2. stderr JSONL is the right transport

| Transport | Verdict | Reason |
|-----------|---------|--------|
| **stderr JSONL** | ✅ Best | No setup, works in process mode, stdout stays clean, Pi doesn't write JSONL to stderr |
| stdout prefix | ❌ | Violates "stdout must remain clean" — Vox treats stdout as final result |
| Unix socket | ❌ | Filesystem path management, cleanup on crash, over-engineered for same-process |
| Named pipe (FIFO) | ❌ | Requires creation before Pi launch, hangs if Pi doesn't open, cleanup |
| TCP localhost | ❌ | Port allocation, over-engineered |
| Env var / exit code only | ❌ | Too coarse — can't distinguish started/processing/completed |

In `--print` mode, `process.stderr.write()` in an extension goes to the process's real stderr. Pi's own stderr output (warnings, extension error logs) is non-JSON and easily filtered. On second and subsequent invocations with the same `--session-id`, Pi emits no warnings at all — stderr is perfectly clean JSONL.

### 3. Fail-open is verified

- **Extension load error**: Pi exits with code 1, stdout empty. Vox already handles this: `if process.returncode != 0: return error`.
- **Event handler error**: Pi catches it, logs the error to stderr, and continues. The model response still arrives on stdout.
- **Extension missing entirely**: Not applicable — Vox explicitly passes `--extension <path>`. If the file is deleted, Pi fails at load time (same as load error above).
- **Extension file present but corrupted**: Pi exits with code 1. Vox's existing error handling covers this.

In all cases, Vox's existing `delegate_to_pi` error paths (non-zero exit, empty stdout, timeout) remain correct. Lifecycle events are additive signal, not a hard dependency.

### 4. Protocol

Events are JSONL on stderr. Each line is a self-contained JSON object:

```
{"d":"<delegation-id>","s":0,"t":"started","mode":"print","pid":1510451}
{"d":"<delegation-id>","s":1,"t":"processing"}
{"d":"<delegation-id>","s":2,"t":"completed"}
{"d":"<delegation-id>","s":3,"t":"shutdown"}
```

- `d` — delegation correlation ID (`VOX_DELEGATION_ID` env var, unique per tool call)
- `s` — monotonic sequence number (0-based within this invocation)
- `t` — event type: `started`, `processing`, `completed`, `shutdown`
- `mode` — only on `started`: always `"print"` for Vox delegations
- `pid` — only on `started`: Pi process PID

### 5. Correlation model

- One `VOX_DELEGATION_ID` per `delegate_to_pi` call (fresh UUID)
- One `--session-id` per WebRTC connection (survives across delegations)
- Both flow to the extension: session-id via `--session-id`, delegation-id via env var
- Events carry the delegation ID so Vox can match stderr lines to specific tool calls
- Since only one delegation is active per session at a time (serial pipecat turns), the session ID alone would suffice, but per-delegation IDs support future concurrent delegation patterns

### 6. Security analysis

| Concern | Status |
|---------|--------|
| Tools registered | None. Extension calls no `registerTool()`. |
| Commands registered | None. No `registerCommand()`. |
| Filesystem access | None. No fs imports, no `readFile`, no `writeFile`. |
| Network access | None. No `fetch()`, no HTTP client, no `pi.exec()`. |
| Context manipulation | None. No `sendMessage()`, no `appendEntry()`, no `setActiveTools()`. |
| Tool mutation | Not possible. `--no-tools` disables all tools at the Pi level. |
| Global extensions | Blocked. `--no-extensions` prevents discovery. Only the explicit path loads. |
| Bounded output | Each event < 200 bytes serialized. Only 4 events per normal invocation. |
| Cluster mutation | Not possible. Extension has zero I/O beyond stderr writes. |

The read-only boundary is **fully preserved**. The extension cannot:
- Give Pi tools it shouldn't have
- Read or write any files
- Make any network requests
- Modify Pi's system prompt, context, or session state
- Communicate with anything except its parent process via stderr

## Minimal integration changes (not yet applied)

### tools.py changes

```python
# 1. Add extension path constant (near the other PI_ constants)
VOX_LIFECYCLE_EXTENSION = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "extensions",
    "vox-lifecycle.ts",
)

# 2. Add per-delegation ID generation
import uuid as _uuid  # at module top

# 3. In delegate_to_pi(), before creating the subprocess:
delegation_id = f"vox-{_uuid.uuid4().hex}"

# 4. Add --extension to the pi argv:
#    "--extension", VOX_LIFECYCLE_EXTENSION,

# 5. Add VOX_DELEGATION_ID to the subprocess env:
env = {**os.environ, "VOX_DELEGATION_ID": delegation_id}

# 6. Pass env=env to create_subprocess_exec (replaces the default env inheritance)

# 7. After process.communicate(), parse stderr for lifecycle events:
from vox_lifecycle import parse_lifecycle_events
events = parse_lifecycle_events(error, delegation_id)
# events is a list of dicts, e.g.:
# [{"d": "...", "s": 0, "t": "started", ...}, ...]

# 8. Optionally include lifecycle summary in the result_callback:
await params.result_callback({
    "response": output,
    "truncated": truncated,
    "lifecycle": {
        "delegation_id": delegation_id,
        "events": [e["t"] for e in events],
    },
})
```

### bot.py changes

No changes required. The `_tool_filler` function already handles `delegate_to_pi` filler narration. Lifecycle events on stderr are consumed by `tools.py` before the result reaches `bot.py`.

### Optional: vox_lifecycle.py helper module

Extract the stderr parser into a shared module so both `tools.py` and tests can use it:

```python
# experiments/pipecat-web-voice/vox_lifecycle.py
import json

def parse_lifecycle_events(stderr: str, delegation_id: str) -> list[dict]:
    """Extract JSONL lifecycle events from Pi stderr, filtered by delegation_id."""
    events = []
    for line in stderr.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("d") == delegation_id:
            events.append(obj)
    return events
```

## What was NOT done

- No modifications to bot.py, tools.py, or the running Vox process
- No changes to Pi's global extension directory
- No systemd or deployment changes
- No new dependencies added to pyproject.toml
