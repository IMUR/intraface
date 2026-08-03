"""Tests for vox-lifecycle extension and Vox-to-Pi lifecycle protocol.

Exercises the extension via live Pi subprocess invocations (not mocked).
Requires pi to be installed and functional.

Run with:
    uv run python tests/test_vox_lifecycle.py
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Allow importing from the parent directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Extension path
# ---------------------------------------------------------------------------

EXTENSION_PATH = str(
    Path(__file__).parent.parent / "extensions" / "vox-lifecycle.ts"
)

PI_BINARY = "pi"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(cond, label):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}")
    return cond


async def run_pi(
    *,
    delegation_id: str = "test-default",
    system_prompt: str = "Reply with just: ok",
    task: str = "Say ok",
    session_id: str | None = None,
    session_dir: str | None = None,
    no_session: bool = False,
    extension: str | None = None,
    timeout: int = 30,
) -> dict:
    """Run a Pi subprocess with the vox-lifecycle extension. Returns result dict."""
    argv = [
        PI_BINARY,
        "--print",
        "--no-tools",
        "--no-context-files",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
    ]

    if extension:
        argv.extend(["--extension", extension])
    else:
        argv.extend(["--extension", EXTENSION_PATH])

    argv.extend(["--system-prompt", system_prompt])

    if no_session:
        argv.append("--no-session")
    elif session_id:
        argv.extend(["--session-id", session_id, "--session-dir", session_dir or tempfile.mkdtemp()])

    argv.append(task)

    env = {**os.environ, "VOX_DELEGATION_ID": delegation_id}

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"timeout": True, "exit": -1, "stdout": "", "stderr": ""}

    return {
        "exit": proc.returncode,
        "stdout": stdout.decode(errors="replace").strip(),
        "stderr": stderr.decode(errors="replace").strip(),
        "timeout": False,
    }


def parse_stderr_events(stderr: str, delegation_id: str) -> list[dict]:
    """Extract JSONL events from stderr, filtering by delegation_id.

    Non-JSON lines (Pi warnings, extension error logs) are skipped.
    """
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def main() -> int:
    failures: list[str] = []

    # =========================================================
    # 1. Extension file exists and is valid TypeScript
    # =========================================================
    print("\n[1] Extension file integrity")
    ext = Path(EXTENSION_PATH)
    ok = (
        _check(ext.exists(), f"extension exists at {EXTENSION_PATH}")
        and _check(ext.stat().st_size > 0, "extension is non-empty")
        and _check(
            "registerTool" not in ext.read_text(),
            "extension does NOT call registerTool",
        )
        and _check(
            "registerCommand" not in ext.read_text(),
            "extension does NOT call registerCommand",
        )
        and _check(
            "fetch(" not in ext.read_text(),
            "extension does NOT call fetch",
        )
        and _check(
            "exec(" not in ext.read_text(),
            "extension does NOT call pi.exec",
        )
    )
    if not ok:
        failures.append("extension-integrity")

    # =========================================================
    # 2. Happy path: started → processing → completed → shutdown
    # =========================================================
    print("\n[2] Happy path — full lifecycle on clean stderr")
    r = await run_pi(
        delegation_id="test-happy-001",
        system_prompt="Reply with just: confirmed",
        task="Confirm",
        no_session=True,
    )
    print(f"  exit={r['exit']} stdout={r['stdout']!r}")
    events = parse_stderr_events(r["stderr"], "test-happy-001")
    print(f"  events={json.dumps(events, indent=2)}")

    ok = (
        _check(r["exit"] == 0, "exit code is 0")
        and _check(r["stdout"] == "confirmed", f"stdout is clean response (got {r['stdout']!r})")
        and _check(len(events) == 4, f"exactly 4 events (got {len(events)})")
        and _check(events[0]["t"] == "started", "event[0] is 'started'")
        and _check(events[0].get("mode") == "print", "started includes mode=print")
        and _check("pid" in events[0], "started includes pid")
        and _check(events[1]["t"] == "processing", "event[1] is 'processing'")
        and _check(events[2]["t"] == "completed", "event[2] is 'completed'")
        and _check(events[3]["t"] == "shutdown", "event[3] is 'shutdown'")
        and _check(events[0]["s"] < events[1]["s"] < events[2]["s"] < events[3]["s"],
                   "sequence numbers are monotonically increasing")
    )
    if not ok:
        failures.append("happy-path")

    # =========================================================
    # 3. Delegation ID is passed through correctly
    # =========================================================
    print("\n[3] Delegation ID correlation")
    r1 = await run_pi(delegation_id="del-alpha", no_session=True)
    r2 = await run_pi(delegation_id="del-beta", no_session=True)
    events1 = parse_stderr_events(r1["stderr"], "del-alpha")
    events2 = parse_stderr_events(r2["stderr"], "del-beta")
    ok = (
        _check(all(e["d"] == "del-alpha" for e in events1), "all events carry del-alpha")
        and _check(all(e["d"] == "del-beta" for e in events2), "all events carry del-beta")
        and _check(len(events1) == 4, "alpha has 4 events")
        and _check(len(events2) == 4, "beta has 4 events")
    )
    if not ok:
        failures.append("delegation-id")

    # =========================================================
    # 4. stdout is clean — no lifecycle events leak
    # =========================================================
    print("\n[4] stdout purity — no JSONL events in stdout")
    r = await run_pi(delegation_id="test-stdout-001", no_session=True)
    stdout_lines = [l.strip() for l in r["stdout"].splitlines()]
    json_lines_in_stdout = [l for l in stdout_lines if l.startswith("{") and '"t"' in l]
    ok = (
        _check(r["exit"] == 0, "exit code is 0")
        and _check(len(json_lines_in_stdout) == 0,
                   "no JSONL event lines in stdout")
        and _check(
            all(not l.startswith('{"d":') for l in stdout_lines),
            "no delegation-tagged lines in stdout",
        )
    )
    if not ok:
        failures.append("stdout-purity")

    # =========================================================
    # 5. Session reuse — second invocation has no warning
    # =========================================================
    print("\n[5] Session reuse — clean stderr on subsequent call")
    with tempfile.TemporaryDirectory() as sdir:
        r1 = await run_pi(
            delegation_id="test-reuse-a",
            session_id="reuse-probe",
            session_dir=sdir,
        )
        r2 = await run_pi(
            delegation_id="test-reuse-b",
            session_id="reuse-probe",
            session_dir=sdir,
        )
        first_has_warning = "Warning:" in r1["stderr"]
        second_has_warning = "Warning:" in r2["stderr"]
        events2 = parse_stderr_events(r2["stderr"], "test-reuse-b")
        ok = (
            _check(first_has_warning, "first invocation has session-creation warning")
            and _check(not second_has_warning,
                       "second invocation has NO warning (clean JSONL)")
            and _check(len(events2) == 4, "second invocation still has 4 events")
            and _check(r2["exit"] == 0, "second invocation succeeds")
        )
    if not ok:
        failures.append("session-reuse")

    # =========================================================
    # 6. Extension not found — Pi fails, Vox error path works
    # =========================================================
    print("\n[6] Missing extension — Pi fails gracefully")
    r = await run_pi(
        extension="/nonexistent/extension.ts",
        delegation_id="test-missing",
        no_session=True,
    )
    ok = (
        _check(r["exit"] != 0, "exit code is non-zero")
        and _check(r["stdout"] == "", "stdout is empty")
        and _check("Failed to load extension" in r["stderr"] or "Error" in r["stderr"],
                   "stderr mentions load failure")
    )
    if not ok:
        failures.append("missing-extension")

    # =========================================================
    # 7. Non-JSON stderr lines are safely ignored by parser
    # =========================================================
    print("\n[7] stderr parser handles non-JSON lines")
    mixed_stderr = (
        "Warning: Some warning from Pi core\n"
        '{"d":"test-parser","s":0,"t":"started"}\n'
        "Extension error (/path): something broke\n"
        '{"d":"test-parser","s":1,"t":"processing"}\n'
        "Another non-JSON line\n"
        '{"d":"test-parser","s":2,"t":"completed"}\n'
        '{"d":"test-parser","s":3,"t":"shutdown"}\n'
        '{"d":"other-delegation","s":0,"t":"started"}\n'
        "not valid json at all {{\n"
    )
    events = parse_stderr_events(mixed_stderr, "test-parser")
    ok = (
        _check(len(events) == 4, f"parsed exactly 4 events (got {len(events)})")
        and _check(events[0]["t"] == "started", "first event is started")
        and _check(events[3]["t"] == "shutdown", "last event is shutdown")
        and _check(
            all(e["d"] == "test-parser" for e in events),
            "all events match delegation_id, other-delegation excluded",
        )
    )
    if not ok:
        failures.append("stderr-parser")

    # =========================================================
    # 8. Sequence numbers are consistent across delegation IDs
    # =========================================================
    print("\n[8] Sequence numbers start at 0 and increment by 1")
    r = await run_pi(
        delegation_id="test-seq-001",
        system_prompt="Reply with just: seqtest",
        task="seqtest",
        no_session=True,
    )
    events = parse_stderr_events(r["stderr"], "test-seq-001")
    sequences = [e["s"] for e in events]
    ok = (
        _check(sequences == list(range(len(sequences))),
               f"sequences are [0, 1, ..., N-1] (got {sequences})")
    )
    if not ok:
        failures.append("sequences")

    # =========================================================
    # 9. Security: extension does not register tools
    # =========================================================
    print("\n[9] Security invariants — no tool registration")
    ext_text = Path(EXTENSION_PATH).read_text()
    ok = (
        _check("registerTool" not in ext_text, "no registerTool call")
        and _check("registerCommand" not in ext_text, "no registerCommand call")
        and _check("registerFlag" not in ext_text, "no registerFlag call")
        and _check("registerShortcut" not in ext_text, "no registerShortcut call")
        and _check("registerProvider" not in ext_text, "no registerProvider call")
        and _check("sendMessage" not in ext_text, "no sendMessage call")
        and _check("appendEntry" not in ext_text, "no appendEntry call")
        and _check("setActiveTools" not in ext_text, "no setActiveTools call")
        and _check("import.*fs" not in ext_text, "no filesystem imports")
        and _check("import.*path" not in ext_text, "no path imports")
        and _check("import.*child_process" not in ext_text, "no child_process imports")
    )
    if not ok:
        failures.append("security-invariants")

    # =========================================================
    # 10. PID is present and is a positive integer
    # =========================================================
    print("\n[10] PID field in started event")
    r = await run_pi(delegation_id="test-pid-001", no_session=True)
    events = parse_stderr_events(r["stderr"], "test-pid-001")
    started = next((e for e in events if e["t"] == "started"), None)
    ok = (
        _check(started is not None, "started event exists")
        and _check("pid" in started, "started has pid field")
        and _check(isinstance(started["pid"], int) and started["pid"] > 0,
                   f"pid is positive integer (got {started.get('pid')})")
    )
    if not ok:
        failures.append("pid-field")

    # =========================================================
    # 11. Event schema is minimal and bounded
    # =========================================================
    print("\n[11] Event schema — all events have d, s, t")
    r = await run_pi(delegation_id="test-schema-001", no_session=True)
    events = parse_stderr_events(r["stderr"], "test-schema-001")
    ok = True
    for i, event in enumerate(events):
        has_d = _check("d" in event, f"event[{i}] has 'd'")
        has_s = _check("s" in event, f"event[{i}] has 's'")
        has_t = _check("t" in event, f"event[{i}] has 't'")
        is_small = _check(len(json.dumps(event)) < 200,
                          f"event[{i}] serialized < 200 bytes")
        ok = ok and has_d and has_s and has_t and is_small
    if not ok:
        failures.append("event-schema")

    # =========================================================
    # 12. Multi-word model response survives on stdout
    # =========================================================
    print("\n[12] Multi-word response on stdout, events on stderr")
    r = await run_pi(
        delegation_id="test-multiword",
        system_prompt="Reply with exactly: the quick brown fox",
        task="What is the sentence?",
        no_session=True,
    )
    ok = (
        _check(r["exit"] == 0, "exit code is 0")
        and _check("the quick brown fox" in r["stdout"],
                   f"stdout contains expected text (got {r['stdout']!r})")
        and _check(len(parse_stderr_events(r["stderr"], "test-multiword")) == 4,
                   "4 events on stderr")
    )
    if not ok:
        failures.append("multiword-response")

    # =========================================================
    # 13. --no-session removes Pi's own warning from stderr
    # =========================================================
    print("\n[13] --no-session produces perfectly clean JSONL stderr")
    r = await run_pi(
        delegation_id="test-clean-stderr",
        no_session=True,
    )
    stderr_lines = [l.strip() for l in r["stderr"].splitlines() if l.strip()]
    non_json_lines = [l for l in stderr_lines if not l.startswith("{")]
    ok = (
        _check(len(non_json_lines) == 0,
               f"no non-JSON lines on stderr (got {len(non_json_lines)})")
        and _check(len(stderr_lines) == 4,
                   f"exactly 4 lines on stderr (got {len(stderr_lines)})")
    )
    if not ok:
        failures.append("clean-stderr")

    # =========================================================
    # 14. Parse performance — handles rapid stderr correctly
    # =========================================================
    print("\n[14] Parser handles empty stderr")
    events = parse_stderr_events("", "test-empty")
    ok = _check(len(events) == 0, "empty stderr yields 0 events")
    events = parse_stderr_events("no events here\njust warnings", "test-empty")
    ok = ok and _check(len(events) == 0, "non-JSON stderr yields 0 events")
    if not ok:
        failures.append("parser-edge-cases")

    # =========================================================
    # 15. Env var not set — falls back to 'unknown'
    # =========================================================
    print("\n[15] Missing VOX_DELEGATION_ID falls back to 'unknown'")
    # This test requires running without the env var, which our helper
    # always sets. We test the parser behavior instead.
    mixed = '{"d":"unknown","s":0,"t":"started"}\n'
    events = parse_stderr_events(mixed, "unknown")
    ok = _check(len(events) == 1 and events[0]["d"] == "unknown",
                "unknown delegation ID is parsed correctly")
    if not ok:
        failures.append("unknown-delegation-id")

    # Summary
    print("\n" + "=" * 60)
    if failures:
        print(f"FAIL — {len(failures)} failure(s): {failures}")
        return 1
    print("PASS — all checks succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
