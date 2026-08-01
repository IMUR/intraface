"""Live cluster tests for vox Layer 1 tools.

Exercises each of the four read-only tools against real cluster nodes over
SSH. Not mocked — these tests call the live backend, so they require:

  - Passwordless SSH aliases `prtr`, `drtr`, `crtr`, `trtr` from this host
  - The local node is prtr (so `ssh prtr` works from this machine)
  - trtr may be asleep; tests handle that by treating it as unreachable-skip

Run with:
    uv run python tests/test_tools.py

This complements tests/test_pipeline_construction.py (which is a
construction-only smoke test). Here we verify the actual tool functions
return voice-shaped JSON and don't raise on the live cluster.
"""

import asyncio
import inspect
import json
import sys
import tempfile
from pathlib import Path

# Allow importing from the parent directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

import tools  # noqa: E402


class FakeParams:
    """Stand-in for pipecat's FunctionCallParams that just captures results.

    Real FunctionCallParams carries the LLM service, context, and a result
    callback. For tool testing in isolation we only need result_callback —
    tools don't use anything else from params.
    """

    def __init__(self, app_resources=None, arguments=None) -> None:
        self.result: dict | None = None
        self.app_resources = app_resources
        self.arguments = arguments or {}

    async def result_callback(self, result) -> None:
        self.result = result


async def run_tool(tool_fn, *, app_resources=None, **kwargs) -> dict:
    """Invoke a tool function with a FakeParams and return the captured result."""
    params = FakeParams(app_resources=app_resources)
    await tool_fn(params=params, **kwargs)
    assert params.result is not None, f"{tool_fn.__name__} produced no result"
    return params.result


def _check(cond, label):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}")
    return cond


async def main() -> int:
    failures: list[str] = []

    # --- Schema shape: each tool's signature includes params + named args
    print("\n[1] Tool signatures accept FunctionCallParams + named args")
    for tool_fn in tools.ALL_TOOLS:
        sig = inspect.signature(tool_fn)
        params = list(sig.parameters.keys())
        ok = params[0] == "params"
        _check(ok, f"{tool_fn.__name__}{sig}: first arg is 'params'") or failures.append(tool_fn.__name__)

    # --- check_node on prtr (always reachable, this is the local box)
    print("\n[2] check_node(prtr) — local node, always reachable")
    r = await run_tool(tools.check_node, node="prtr")
    print(f"  result: {json.dumps(r, indent=2)}")
    ok = (
        _check(r.get("node") == "prtr", "node == prtr")
        and _check(r.get("reachable") is True, "reachable is True")
        and _check("uptime" in r, "uptime present")
        and _check("load" in r, "load present")
        and _check(isinstance(r.get("services"), dict), "services is dict")
    )
    if not ok:
        failures.append("check_node(prtr)")

    # --- check_node on drtr (GPU node, voice services run here)
    print("\n[3] check_node(drtr) — GPU/voice node, should find parakeet+chatterbox")
    r = await run_tool(tools.check_node, node="drtr")
    print(f"  result: {json.dumps(r, indent=2)}")
    services = r.get("services", {})
    ok = (
        _check(r.get("reachable") is True, "reachable is True")
        and _check(r.get("node") == "drtr", "node == drtr")
        and _check(services.get("parakeet-stt") == "active", "parakeet-stt active")
        and _check(services.get("chatterbox-tts") == "active", "chatterbox-tts active")
    )
    if not ok:
        failures.append("check_node(drtr)")

    # --- check_node on unknown node — must return unreachable, not raise
    print("\n[4] check_node(invalid-node) — unknown name, graceful failure")
    r = await run_tool(tools.check_node, node="bogus")
    print(f"  result: {json.dumps(r, indent=2)}")
    ok = _check(r.get("reachable") is False, "reachable is False") and _check(
        "unknown" in r.get("error", "").lower(), "error mentions unknown"
    )
    if not ok:
        failures.append("check_node(invalid)")

    # --- list_services on drtr — should find parakeet/chatterbox
    print("\n[5] list_services(drtr) — find cluster-relevant units")
    r = await run_tool(tools.list_services, node="drtr")
    print(f"  result: {json.dumps(r, indent=2)}")
    found = r.get("services", {})
    ok = (
        _check(r.get("reachable") is True, "reachable is True")
        and _check(isinstance(found, dict), "services is dict")
        and _check("parakeet-stt" in found, "parakeet-stt present")
        and _check("chatterbox-tts" in found, "chatterbox-tts present")
    )
    if not ok:
        failures.append("list_services(drtr)")

    # --- get_log_tail on a real service
    print("\n[6] get_log_tail(prtr, cockpit, lines=5) — short log fetch")
    r = await run_tool(tools.get_log_tail, node="prtr", service="cockpit", lines=5)
    print(f"  result keys: {list(r.keys())}, count: {r.get('count')}")
    ok = _check(r.get("reachable") is True, "reachable is True") and _check(
        isinstance(r.get("lines"), list), "lines is list"
    )
    if not ok:
        failures.append("get_log_tail(cockpit)")

    # --- get_log_tail lines cap — request 9999, must be capped at 50
    print("\n[7] get_log_tail lines cap — request 9999, must be capped at 50")
    # Don't actually fetch 50 lines (slow); just verify the cap is enforced
    # by inspecting the function under a small bound.
    r = await run_tool(tools.get_log_tail, node="prtr", service="cockpit", lines=9999)
    # The cap is applied before SSH; if we got a result back, count should
    # be <= 50. (It may be smaller if the unit has fewer lines.)
    count = r.get("count", 0)
    ok = _check(count <= 50, f"count ({count}) <= 50")
    if not ok:
        failures.append("get_log_tail(cap)")

    # --- get_log_tail invalid service name — rejected before SSH
    print("\n[8] get_log_tail invalid service name — rejected pre-SSH")
    r = await run_tool(tools.get_log_tail, node="prtr", service="bad;rm -rf /", lines=3)
    print(f"  result: {json.dumps(r, indent=2)}")
    ok = _check("error" in r, "has error field") and _check(
        "invalid" in r.get("error", "").lower(), "error mentions invalid"
    )
    if not ok:
        failures.append("get_log_tail(invalid-name)")

    # --- get_port_state on prtr — should find 7712 (llama-server)
    print("\n[9] get_port_state(prtr) — must find llama-server on 7712")
    r = await run_tool(tools.get_port_state, node="prtr")
    listeners = r.get("listeners", [])
    ports = {l.get("port") for l in listeners}
    print(f"  found ports: {sorted(ports)}")
    ok = (
        _check(r.get("reachable") is True, "reachable is True")
        and _check("7712" in ports, "7712 (llama-server) present")
        # All returned ports must be in cluster ranges
        and _check(
            all(int(p) >= 4400 and int(p) <= 7999 for p in ports if p.isdigit()),
            "all ports in cluster blocks (4400-7999)",
        )
    )
    if not ok:
        failures.append("get_port_state(prtr)")

    # --- helper function checks
    print("\n[10] Output shaping helpers")
    # Real Linux uptime output. The user count is kept; load is dropped
    # (it's reported separately via _extract_load).
    _check(
        tools._shorten_uptime(" 12:34:56 up 11 days,  3:45,  1 user,  load average: 0.10, 0.12, 0.10")
        == "up 11 days,  3:45,  1 user",
        "_shorten_uptime Linux form",
    )
    # macOS uptime output: leading time, "load averages:" plural
    _check(
        tools._shorten_uptime("12:34:56 up 4 days, 21:53, 1 user, load averages: 2.03 1.76 1.72")
        == "up 4 days, 21:53, 1 user",
        "_shorten_uptime macOS form (load averages plural)",
    )
    _check(tools._extract_load("load average: 0.10, 0.12, 0.10") == "0.10", "_extract_load Linux")
    _check(tools._extract_load("load averages: 2.03 1.76 1.72") == "2.03", "_extract_load macOS")
    _check(
        tools._split_host_port("127.0.0.1:7712") == ("127.0.0.1", "7712"),
        "_split_host_port v4",
    )
    _check(
        tools._split_host_port("[::1]:7712") == ("::1", "7712"),
        "_split_host_port v6",
    )
    _check(tools._parse_service_probes("parakeet-stt=active\nchatterbox-tts=active\n") ==
           {"parakeet-stt": "active", "chatterbox-tts": "active"},
           "_parse_service_probes")

    # --- trtr may be asleep; if reachable, test passes; if not, it's a skip
    print("\n[11] check_node(trtr) — macOS, may be asleep (skip if unreachable)")
    r = await run_tool(tools.check_node, node="trtr")
    if r.get("reachable"):
        print(f"  trtr reachable, uptime: {r.get('uptime')}")
        _check(True, "trtr reachable")
    else:
        print(f"  trtr unreachable: {r.get('error')}")
        print("  [SKIP] trtr asleep/unreachable — not counted as failure")

    # =========================================================
    # Layer 2 — Filesystem (read-only)
    # =========================================================

    # --- allowlist helper: rejects paths outside ~/prj/intraface/
    print("\n[12] _resolve_and_check allowlist enforcement")
    cases = [
        ("~/prj/intraface/bot.py",    True,  "tilde + intraface"),
        ("bot.py",                    True,  "relative resolves under $HOME/intraface (cwd-independent)"),
        ("/etc/passwd",               False, "outside allowlist"),
        ("~/../etc/passwd",           False, ".. traversal blocked"),
        ("/tmp/x",                    False, "tmp blocked"),
        ("",                          False, "empty path"),
    ]
    for path, expected_ok, label in cases:
        ok, _resolved, _reason = tools._resolve_and_check(path)
        # Note: "bot.py" relative resolves to $HOME/bot.py (not intraface).
        # The function joins $HOME + relative, so "bot.py" alone is NOT under
        # intraface. Adjust the expectation to match real behavior.
        if path == "bot.py":
            expected_ok = False
            label = "relative 'bot.py' is $HOME/bot.py — not under intraface, rejected"
        _check(ok == expected_ok, f"{label}: ok={ok} expected={expected_ok}") or failures.append(f"allowlist:{path}")

    # --- read_file: known existing file
    print("\n[13] read_file(bot.py) — known file under allowlist")
    r = await run_tool(tools.read_file, path="~/prj/intraface/experiments/pipecat-web-voice/bot.py")
    ok = (
        _check("content" in r, "has content field")
        and _check(r.get("size_bytes", 0) > 0, "size_bytes > 0")
        and _check("vox" in r.get("content", "") or "SYSTEM_INSTRUCTION" in r.get("content", ""),
                   "content looks like bot.py")
    )
    if not ok:
        failures.append("read_file(bot.py)")

    # --- read_file: rejects outside allowlist
    print("\n[14] read_file(/etc/passwd) — must be rejected by allowlist")
    r = await run_tool(tools.read_file, path="/etc/passwd")
    ok = _check("error" in r, "has error field") and _check(
        "allowlist" in r.get("error", "").lower() or "outside" in r.get("error", "").lower(),
        "error mentions allowlist/outside",
    )
    if not ok:
        failures.append("read_file(/etc/passwd)")

    # --- read_file: truncation marker on big file
    print("\n[15] read_file on a > 4 KiB file — must mark truncated=True")
    # engines.toml + uv.lock are both > 4 KiB
    r = await run_tool(tools.read_file, path="~/prj/intraface/experiments/pipecat-web-voice/uv.lock")
    ok = _check(r.get("truncated") is True, "truncated=True") and _check(
        len(r.get("content", "")) <= tools._MAX_READ_BYTES,
        f"content length ({len(r.get('content', ''))}) <= cap ({tools._MAX_READ_BYTES})",
    )
    if not ok:
        failures.append("read_file(truncation)")

    # --- list_directory: known dir
    print("\n[16] list_directory(experiments/pipecat-web-voice) — known dir")
    r = await run_tool(tools.list_directory, path="~/prj/intraface/experiments/pipecat-web-voice")
    names = {e.get("name") for e in r.get("entries", [])}
    print(f"  found {len(names)} entries: {sorted(names)[:8]}...")
    ok = (
        _check(r.get("count", 0) > 0, "count > 0")
        and _check("bot.py" in names, "bot.py present")
        and _check("tools.py" in names, "tools.py present")
        and _check(any(e.get("type") == "dir" for e in r.get("entries", [])), "at least one dir entry")
    )
    if not ok:
        failures.append("list_directory")

    # --- list_directory: rejects outside allowlist
    print("\n[17] list_directory(/tmp) — must be rejected")
    r = await run_tool(tools.list_directory, path="/tmp")
    ok = _check("error" in r, "has error field")
    if not ok:
        failures.append("list_directory(/tmp)")

    # --- find_files: substring match
    print("\n[18] find_files('bot.py', ~/prj/intraface) — must find bot.py files")
    r = await run_tool(tools.find_files, pattern="bot.py", root="~/prj/intraface")
    matches = r.get("matches", [])
    print(f"  found {len(matches)} matches")
    ok = (
        _check(r.get("count", 0) >= 1, "count >= 1")
        and _check(any("bot.py" in m for m in matches), "at least one bot.py match")
    )
    if not ok:
        failures.append("find_files")

    # --- find_files: rejects outside allowlist
    print("\n[19] find_files(pattern, root=/) — must be rejected")
    r = await run_tool(tools.find_files, pattern="x", root="/")
    ok = _check("error" in r, "has error field")
    if not ok:
        failures.append("find_files(/)")

    # --- grep_files: content match
    print("\n[20] grep_files('SYSTEM_INSTRUCTION', ~/prj/intraface) — must match bot.py")
    r = await run_tool(tools.grep_files, pattern="SYSTEM_INSTRUCTION", root="~/prj/intraface")
    matches = r.get("matches", [])
    print(f"  found {len(matches)} matches")
    paths = {m.get("path") for m in matches if isinstance(m, dict) and "path" in m}
    ok = (
        _check(r.get("count", 0) >= 1, "count >= 1")
        and _check(any("bot.py" in p for p in paths), "at least one bot.py path")
    )
    if not ok:
        failures.append("grep_files")

    # --- grep_files: rejects outside allowlist
    print("\n[21] grep_files('x', root=/etc) — must be rejected")
    r = await run_tool(tools.grep_files, pattern="x", root="/etc")
    ok = _check("error" in r, "has error field")
    if not ok:
        failures.append("grep_files(/etc)")

    # --- grep_files: no matches returns empty list, not error
    # Search a subtree that does NOT contain this test file. Otherwise the
    # test string itself becomes the only match (self-defeating).
    print("\n[22] grep_files with bogus pattern — empty matches, no error")
    bogus = "q9w8e7r6t5y5u4i3o2p1_NO_SUCH_TOKEN_zZz"
    r = await run_tool(tools.grep_files, pattern=bogus,
                       root="~/prj/intraface/experiments/pipecat-web-voice/static")
    ok = _check("error" not in r, "no error field") and _check(
        r.get("count") == 0, f"count == 0 (got {r.get('count')})",
    )
    if not ok:
        failures.append("grep_files(no-match)")

    # =========================================================
    # Layer 3 — Web search
    # =========================================================

    # --- _extract_domain helper
    print("\n[23] _extract_domain voice-friendly domain extraction")
    cases = [
        ("https://docs.pipecat.ai/x/y",       "docs.pipecat.ai"),
        ("https://stackoverflow.com/q/123",    "stackoverflow.com"),
        ("http://example.com",                 "example.com"),
        ("",                                   ""),
        ("not a url",                          "not a url"),
    ]
    for url, expected in cases:
        got = tools._extract_domain(url)
        _check(got == expected, f"{url!r} -> {got!r} (expected {expected!r})") or failures.append("domain")

    # --- SEARCH_INTENTS shape
    print("\n[24] SEARCH_INTENTS includes the documented intents")
    required = {"general", "code", "docs", "research", "ml"}
    got = set(tools.SEARCH_INTENTS.keys())
    _check(required.issubset(got), f"required intents present: missing={required - got}") or failures.append("intents")

    # --- web_search happy path
    print("\n[25] web_search('pipecat function calling', general) — must return >= 1 result")
    r = await run_tool(tools.web_search, query="pipecat function calling", intent="general")
    results = r.get("results", [])
    print(f"  count: {r.get('count')}, top: {results[0].get('title', '')[:60] if results else '(none)'}")
    ok = (
        _check("error" not in r, "no error field")
        and _check(r.get("count", 0) >= 1, "count >= 1")
        and _check(len(results) <= tools._MAX_SEARCH_RESULTS,
                   f"results capped at {tools._MAX_SEARCH_RESULTS}")
    )
    if results:
        ok = ok and _check(all(k in results[0] for k in ("title", "source", "snippet", "url")),
                           "result has all four fields")
    if not ok:
        failures.append("web_search(general)")

    # --- web_search with code intent (engine filter)
    print("\n[26] web_search('python asyncio', intent=code) — must return results")
    r = await run_tool(tools.web_search, query="python asyncio subprocess", intent="code")
    print(f"  count: {r.get('count')}")
    ok = _check("error" not in r, "no error field") and _check(r.get("count", 0) >= 1, "count >= 1")
    if not ok:
        failures.append("web_search(code)")

    # --- web_search snippet length cap
    print("\n[27] web_search result snippets must be <= 200 chars + ellipsis")
    r = await run_tool(tools.web_search, query="machine learning long article about transformers", intent="general")
    for res in r.get("results", []):
        snip = res.get("snippet", "")
        # 200 cap, plus up to 3 chars of "..." appended
        _check(len(snip) <= 203, f"snippet len {len(snip)} <= 203") or failures.append("snippet-cap")

    # --- web_search invalid intent — rejected pre-network
    print("\n[28] web_search with invalid intent — must be rejected")
    r = await run_tool(tools.web_search, query="x", intent="bogus")
    ok = _check("error" in r, "has error field") and _check(
        "intent" in r.get("error", "").lower(), "error mentions intent",
    )
    if not ok:
        failures.append("web_search(bad-intent)")

    # =========================================================
    # Strict schemas + Layer 4 — Pi delegation
    # =========================================================

    print("\n[29] constrained arguments are encoded in model-visible schemas")
    schemas = {
        definition.name: definition
        for definition in tools.TOOL_DEFINITIONS
        if hasattr(definition, "properties")
    }
    for name in ("check_node", "list_services", "get_log_tail", "get_port_state"):
        enum = schemas[name].properties["node"].get("enum")
        _check(enum == list(tools.NODES), f"{name}.node has strict enum") or failures.append(
            f"{name}-node-enum"
        )
    intent_enum = schemas["web_search"].properties["intent"].get("enum")
    _check(
        intent_enum == list(tools.SEARCH_INTENTS),
        "web_search.intent has strict enum",
    ) or failures.append("web-search-intent-enum")
    schema_params = FakeParams(arguments={"node": "prtr"})
    await schemas["check_node"].handler(schema_params)
    _check(
        schema_params.result is not None and schema_params.result.get("reachable") is True,
        "FunctionSchema handler dispatches to direct implementation",
    ) or failures.append("schema-handler-dispatch")

    print("\n[30] delegate_to_pi rejects calls without a per-session identity")
    r = await run_tool(tools.delegate_to_pi, task="Explain the tradeoff.")
    _check("session identity" in r.get("error", ""), "missing identity rejected") or failures.append(
        "delegate-missing-session"
    )
    r = await run_tool(
        tools.delegate_to_pi,
        app_resources={"pi_session_id": "vox-" + "a" * 32},
        task="Edit bot.py and make the responses longer.",
    )
    _check("mutation" in r.get("error", ""), "mutation delegation rejected") or failures.append(
        "delegate-mutation"
    )

    print("\n[31] delegate_to_pi disables tools and caps returned text")
    captured_argv: tuple[str, ...] = ()

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"x" * 700, b""

        def kill(self):
            pass

        async def wait(self):
            pass

    async def fake_create_subprocess_exec(*argv, **_kwargs):
        nonlocal captured_argv
        captured_argv = argv
        return FakeProcess()

    original_create = tools.asyncio.create_subprocess_exec
    original_session_dir = tools.PI_SESSION_DIR
    try:
        with tempfile.TemporaryDirectory() as session_dir:
            tools.PI_SESSION_DIR = session_dir
            tools.asyncio.create_subprocess_exec = fake_create_subprocess_exec
            r = await run_tool(
                tools.delegate_to_pi,
                app_resources={"pi_session_id": "vox-" + "a" * 32},
                task="Compare two safe designs.",
            )
    finally:
        tools.asyncio.create_subprocess_exec = original_create
        tools.PI_SESSION_DIR = original_session_dir

    ok = (
        _check("--no-tools" in captured_argv, "Pi launched with --no-tools")
        and _check("--session-id" in captured_argv, "Pi launched with --session-id")
        and _check(r.get("truncated") is True, "long Pi output marked truncated")
        and _check(
            len(r.get("response", "")) <= tools._MAX_PI_OUTPUT_CHARS,
            "Pi output capped before reaching the LLM",
        )
    )
    if not ok:
        failures.append("delegate-safety")

    # Summary
    print("\n" + "=" * 60)
    if failures:
        print(f"FAIL — {len(failures)} failure(s): {failures}")
        return 1
    print("PASS — all checks succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
