"""Read-only cluster tools for vox.

Layer 1 of the vox capability stack (see AGENTS.md). Four functions, each
SSH-based, each returning voice-shaped JSON the system prompt summarizes into
one spoken sentence. No mutation, no shell=True, no sh -c — every command is
constructed from a fixed shape and the model only picks known arguments
(router test: policy decides shape, model picks args).

The functions are async because pipecat's tool dispatcher awaits them. The
SSH calls use asyncio.create_subprocess_exec so they don't block the event
loop during the ~3-110ms each call takes over the tailnet.

Voice-shape contract:
    - Return short JSON, ~50-100 words of data, never log output
    - Use booleans and short strings, not paragraphs
    - On failure return {"reachable": false, "error": "<short reason>"}
      rather than raising — the system prompt handles the spoken form
"""

import asyncio
import json
import os
import re
import shlex
import urllib.parse
import urllib.request
from typing import Any

from pipecat.services.llm_service import FunctionCallParams

# Cluster topology (mirror of docs/voice-chat-evaluation.md → Reference).
# Single source of truth for tool argument validation — the model gets this
# same enum in each FunctionSchema so it can't ask for a node that doesn't
# exist.
NODES = ("prtr", "drtr", "crtr", "trtr")

# Service patterns matched by list_services. Voice-relevant live services
# plus anything under the intraface state/model trees. Tunable — widen by
# adding patterns here, not by changing the function.
#
# Note: on prtr, the Core (llama-server) and vox itself run as bare nohup
# processes, not systemd units — so list_services(prtr) may legitimately
# return an empty dict. That's a real finding about deployment state, not a
# tool bug. Use get_port_state to see they're listening.
SERVICE_PATTERNS = (
    "parakeet",
    "chatterbox",
    "llama",
    "pipecat",
    "cockpit",
    "caddy",
    "xtdb",
    "ollama",
)

# Port block filter for get_port_state. The cluster uses 44xx/55xx/66xx/77xx
# by category (see docs/voice-chat-evaluation.md → Cluster port block model).
# We display only listeners in these blocks to keep the result voice-shaped.
PORT_BLOCK_RE = re.compile(r":(4[4-9]\d{2}|5[5-9]\d{2}|6[6-9]\d{2}|7[7-9]\d{2})\b")

# trtr is macOS and sleeps; SSH can hang. Other nodes are always-on Debian.
# Timeouts are conservative — if these fire often, the node has a real problem
# and the spoken "unreachable" is the right answer.
_NODE_TIMEOUT_SECS = {"trtr": 5}
_DEFAULT_TIMEOUT_SECS = 10


def _timeout_for(node: str) -> int:
    return _NODE_TIMEOUT_SECS.get(node, _DEFAULT_TIMEOUT_SECS)


async def _ssh(node: str, command: str) -> tuple[bool, str]:
    """Run a command on a cluster node via SSH. Read-only by construction.

    The command is sent as a single shell string to the remote bash login
    shell (`ssh node '<command>'`). This is necessary because several tools
    use shell features (pipes, command substitution) that don't survive
    being split into separate argv entries by create_subprocess_exec.

    Safety rests on the command being constructed from fixed shapes inside
    this module — the model only picks arguments that go through shlex.quote
    or strict regex validation before reaching here. No caller in this file
    interpolates raw user/LLM strings without quoting.

    On ControlMaster-stale failures ("Connection closed" / "bad permissions"
    on the multiplex socket), runs `ssh -O exit <node>` once and retries.

    Returns (ok, output). On timeout or non-zero exit, ok=False and output
    is a short reason suitable for the spoken "unreachable" path. Never
    raises — callers receive the failure as data.
    """
    if node not in NODES:
        return False, f"unknown node '{node}'"

    argv = ["ssh", "-o", "BatchMode=yes", node, command]

    async def _run() -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_timeout_for(node)
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "", "timeout"
        return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")

    returncode, stdout, stderr = await _run()

    # Stale ControlMaster socket: clear it and retry once.
    if returncode != 0 and _looks_like_stale_socket(stderr):
        clear = await asyncio.create_subprocess_exec(
            "ssh", "-O", "exit", node,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await clear.wait()
        returncode, stdout, stderr = await _run()

    if returncode == 0:
        return True, stdout.strip()
    reason = (stderr.strip() or stdout.strip() or f"exit {returncode}")[:200]
    return False, reason


def _looks_like_stale_socket(stderr: str) -> bool:
    markers = ("Connection closed", "bad permissions", "mux_client_request_alive")
    return any(m in stderr for m in markers)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


# Per-node service probes for check_node. Each node has a different set of
# voice/inference-relevant units; checking the right ones gives the user a
# quick "is the stack healthy?" answer without a separate list_services call.
# Tunable — add units here when new services land.
NODE_SERVICES: dict[str, tuple[str, ...]] = {
    "prtr": ("ollama", "cockpit"),
    "drtr": ("parakeet-stt", "chatterbox-tts"),
    "crtr": ("caddy",),
    "trtr": (),
}


async def check_node(params: FunctionCallParams, node: str) -> None:
    """Check if a cluster node is reachable and report basic status.

    Returns uptime, load average, and whether key services are active. Use
    this first when asked "is X up?" or "how's X doing?".

    Args:
        node: Cluster node name — one of: prtr, drtr, crtr, trtr
    """
    # Probe each known service for this node with `systemctl is-active`.
    # Combined into one SSH round-trip via a small bash sequence on the remote
    # side (safer than N separate SSH calls, faster over the tailnet).
    # Each probe is its own statement separated by `;` — `echo a echo b` does
    # not split into two echoes, it prints "a echo b" as one line.
    services_to_check = NODE_SERVICES.get(node, ())
    if services_to_check:
        checks = "; ".join(
            f"echo {name}=$(systemctl is-active {name}.service 2>/dev/null || echo unknown)"
            for name in services_to_check
        )
        cmd = f"uptime; echo '---'; {checks}"
    else:
        cmd = "uptime"

    ok, output = await _ssh(node, cmd)

    if not ok:
        await params.result_callback({
            "node": node,
            "reachable": False,
            "error": "unreachable" if output in ("timeout", "") else output,
        })
        return

    uptime_part, _, services_part = output.partition("---")
    uptime_part = uptime_part.strip()
    services_part = services_part.strip()

    load = _extract_load(uptime_part)
    service_status = _parse_service_probes(services_part)

    await params.result_callback({
        "node": node,
        "reachable": True,
        "uptime": _shorten_uptime(uptime_part),
        "load": load,
        "services": service_status,
    })


async def list_services(params: FunctionCallParams, node: str) -> None:
    """List active systemd services on a node matching cluster patterns.

    Matches the known voice/inference services (parakeet, chatterbox, llama,
    pipecat, cockpit, caddy, xtdb). Returns a {name: active_state} dict.

    Args:
        node: Cluster node name — one of: prtr, drtr, crtr, trtr
    """
    # systemctl list-units --type=service --state=active, then grep -E for
    # the alternation. Quoted as one shell argument to preserve the regex.
    pattern = "|".join(SERVICE_PATTERNS)
    cmd = (
        f"systemctl list-units --type=service --state=active --no-legend --no-pager "
        f"| grep -E '{pattern}' || true"
    )
    ok, output = await _ssh(node, cmd)

    if not ok:
        await params.result_callback({
            "node": node,
            "reachable": False,
            "error": "unreachable" if output in ("timeout", "") else output,
        })
        return

    services = _parse_service_lines(output)
    await params.result_callback({
        "node": node,
        "reachable": True,
        "services": services,
        "count": len(services),
    })


async def get_log_tail(
    params: FunctionCallParams,
    node: str,
    service: str,
    lines: int = 15,
) -> None:
    """Get the last N lines of a service's journalctl log on a node.

    Use for "what's in the X log?" or "did Y error recently?". Returns the
    raw lines plus a short hint about the most recent line so the system
    prompt can summarize without re-parsing.

    Args:
        node: Cluster node name — one of: prtr, drtr, crtr, trtr
        service: systemd unit name (e.g., 'parakeet-stt', 'chatterbox-tts').
            Suffix '.service' is optional.
        lines: Number of lines to return. Default 15. Max 50.
    """
    lines = max(1, min(int(lines), 50))
    # Strip a trailing .service so users can say either form
    unit = service[:-8] if service.endswith(".service") else service
    # Whitelist the unit name to alphanumeric + dash + underscore + dot.
    # journalctl -u is safe with these; anything else is rejected before SSH.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", unit):
        await params.result_callback({
            "node": node,
            "service": service,
            "error": "invalid service name",
        })
        return

    cmd = f"journalctl -u {shlex.quote(unit + '.service')} -n {lines} --no-pager"
    ok, output = await _ssh(node, cmd)

    if not ok:
        await params.result_callback({
            "node": node,
            "service": service,
            "reachable": False,
            "error": "unreachable" if output in ("timeout", "") else output,
        })
        return

    tail = output.splitlines()
    await params.result_callback({
        "node": node,
        "service": unit,
        "reachable": True,
        "lines": tail,
        "count": len(tail),
        "last": tail[-1] if tail else "",
    })


async def get_port_state(params: FunctionCallParams, node: str) -> None:
    """List listening TCP ports on a node within the cluster port blocks.

    Cluster convention: 44xx = daemons, 55xx = web UIs, 66xx = data stores,
    77xx = AI services (STT/TTS/LLM). Returns the matched listeners so the
    spoken summary can say "Core is listening on 7712" without naming every
    ephemeral port on the box.

    Args:
        node: Cluster node name — one of: prtr, drtr, crtr, trtr
    """
    cmd = "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null"
    ok, output = await _ssh(node, cmd)

    if not ok:
        await params.result_callback({
            "node": node,
            "reachable": False,
            "error": "unreachable" if output in ("timeout", "") else output,
        })
        return

    listeners = _parse_port_lines(output)
    await params.result_callback({
        "node": node,
        "reachable": True,
        "listeners": listeners,
        "count": len(listeners),
    })


# ---------------------------------------------------------------------------
# Output shaping helpers (not exported as tools)
# ---------------------------------------------------------------------------


_LOAD_RE = re.compile(r"load averages?:\s*([\d.]+)")


def _extract_load(uptime_line: str) -> str:
    # Matches both "load average:" (Linux) and "load averages:" (macOS).
    m = _LOAD_RE.search(uptime_line)
    return m.group(1) if m else ""


# Matches the `up ...` segment of `uptime` output. Works for both:
#   " 12:34:56 up 11 days,  3:45,  1 user,  load average: 0.10, ..." (Linux)
#   "up 4 days, 21:53, 1 user, load averages: 2.03 1.76 1.72"        (macOS, no leading time)
# Capture group 1 is the segment between `up` and `load average(s):`.
_UPTIME_SEGMENT_RE = re.compile(
    r"\bup\s+(.*?),?\s+load averages?:.*$",
    re.IGNORECASE,
)


def _shorten_uptime(uptime_line: str) -> str:
    """Collapse `uptime` output to the part a voice summary cares about.

    Handles both Linux (`load average:`) and macOS (`load averages:`) forms.
    ` 12:34:56 up 11 days,  3:45,  1 user,  load average: 0.10, 0.12, 0.10`
    becomes `up 11 days,  3:45`. Load is reported separately.
    """
    m = _UPTIME_SEGMENT_RE.search(uptime_line)
    if not m:
        return uptime_line[:80]
    return f"up {m.group(1).strip()}"


def _parse_service_lines(output: str) -> dict[str, str]:
    """Parse `systemctl list-units` non-legend output into {unit: state}."""
    services: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split()
        # Format: UNIT LOAD ACTIVE SUB DESCRIPTION
        if len(parts) < 4:
            continue
        unit, _load, active, *_ = parts
        if unit.endswith(".service"):
            unit = unit[:-8]
        services[unit] = active
    return services


def _parse_service_probes(output: str) -> dict[str, str]:
    """Parse the `name=state` lines emitted by check_node's per-node probe.

    Each line looks like `parakeet-stt=active`. Unknown probes (no unit
    file) come back as `name=unknown` and are included so the spoken summary
    can say "couldn't tell" rather than silently omitting them.
    """
    result: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        name, _, state = line.partition("=")
        result[name.strip()] = state.strip()
    return result


def _parse_port_lines(output: str) -> list[dict[str, str]]:
    """Parse `ss -tlnp` / `netstat -tlnp` output for cluster-port listeners.

    Returns one dict per matched listener: {address, port, process}. Process
    name is best-effort — `ss` shows it as `users:(("name",pid=...,fd=...))`,
    `netstat` shows `pid/name`. We extract just the name.
    """
    listeners: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for line in output.splitlines():
        if not PORT_BLOCK_RE.search(line):
            continue
        # Find the local-address column. ss and netstat both put it after
        # the state column; for LISTEN lines the column count is stable.
        cols = line.split()
        local_addr = ""
        proc = ""
        # ss format: State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
        # when -p is permitted. Netstat: Proto Recv-Q Send-Q Local Address Foreign Address State PID/Program
        if "LISTEN" in line and len(cols) >= 5:
            # ss
            if "users:" in line:
                # Local Address is typically cols[3]
                local_addr = cols[3]
                m = re.search(r'users:\(\("([^"]+)"', line)
                if m:
                    proc = m.group(1)
            else:
                # netstat — Local Address is cols[3]
                local_addr = cols[3]
                m = re.search(r"\d+/(\S+)$", line)
                if m:
                    proc = m.group(1)

        if not local_addr:
            continue

        # Split host:port, handle both v4 and v6 forms
        host, port = _split_host_port(local_addr)
        if not port:
            continue

        key = (host, port)
        if key in seen:
            continue
        seen.add(key)

        listeners.append({"address": host, "port": port, "process": proc})

    return listeners


def _split_host_port(addr: str) -> tuple[str, str]:
    """Split a socket address into (host, port). Handles v4 and bracketed v6."""
    if addr.startswith("["):
        # [v6]:port
        end = addr.find("]")
        if end == -1:
            return addr, ""
        host = addr[1:end]
        rest = addr[end + 1:]
        port = rest[1:] if rest.startswith(":") else ""
        return host, port
    if addr.count(":") == 1:
        host, port = addr.rsplit(":", 1)
        return host, port
    # Bare v6 without port (rare for listeners) or malformed
    return addr, ""


# ---------------------------------------------------------------------------
# Layer 2 — Filesystem awareness (read-only)
# ---------------------------------------------------------------------------

# Path allowlist. Vox can read from these roots and nowhere else. Add a root
# here when a new code/source area becomes relevant; don't widen the function
# to accept arbitrary paths. Symlinks are resolved before this check fires,
# so a symlink inside an allowed root pointing outside will be rejected by
# the realpath check (resolved path won't start with an allowed prefix).
#
# Paths are stored absolute; tilde is expanded at module load. Relative
# inputs from the LLM are resolved against $HOME before the allowlist check.
_ALLOWED_ROOTS: tuple[str, ...] = (
    os.path.expanduser("~/prj/intraface/"),
    "/etc/cluster/",  # placeholder — not present today, but reserves the slot
)

# Hard caps so a single tool call can't dump unbounded data into the LLM
# context or take minutes to return. Tunable — raise if voice patterns call
# for it, but the LLM gets short summaries anyway so big caps don't help.
_MAX_READ_BYTES = 4 * 1024           # read_file: 4 KiB cap
_MAX_LIST_ENTRIES = 50               # list_directory: 50 entries
_MAX_FIND_RESULTS = 50               # find_files: 50 paths
_MAX_GREP_MATCHES = 20               # grep_files: 20 lines


def _resolve_and_check(path: str) -> tuple[bool, str, str]:
    """Resolve a path through the allowlist.

    Returns (allowed, resolved_path, reason). On rejection, allowed=False
    and reason explains why for the spoken "I can't read that" path.
    """
    if not path:
        return False, "", "empty path"

    # Resolve relative paths against $HOME (vox runs as prtr; user-shaped
    # paths like "~/prj/intraface/..." arrive bare). Then realpath to collapse
    # any ".." traversal or symlink indirection before the prefix check.
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        expanded = os.path.join(os.path.expanduser("~"), expanded)

    try:
        resolved = os.path.realpath(expanded)
    except (OSError, RuntimeError) as e:
        return False, "", f"resolution failed: {e}"

    for root in _ALLOWED_ROOTS:
        root_resolved = os.path.realpath(root)
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            return True, resolved, ""

    return False, resolved, "path outside allowlist"


async def _local(*argv: str, timeout: int = 8) -> tuple[bool, str]:
    """Run a command locally. Read-only by construction (callers pass fixed argv).

    Uses create_subprocess_exec with an explicit argv array — no shell
    expansion. Unlike _ssh, local tools use argv form because none of them
    need shell metacharacters; rg accepts its patterns as separate args.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return False, "timeout"
    except FileNotFoundError as e:
        return False, f"missing binary: {e.filename}"

    if proc.returncode == 0:
        return True, stdout_b.decode(errors="replace")
    err = stderr_b.decode(errors="replace").strip()
    return False, err[:200] if err else f"exit {proc.returncode}"


async def read_file(params: FunctionCallParams, path: str) -> None:
    """Read a text file from the local filesystem. Read-only, size-capped.

    Use for "what's in X?" or "show me bot.py" type questions. Returns the
    file contents (up to 4 KiB) plus the total byte count so the spoken
    summary can say "the file is 12 KiB, here's the first part" rather
    than implying the whole thing was read.

    Args:
        path: File path. Relative paths resolve against $HOME. Only paths
            under ~/prj/intraface/ (or other allowlisted roots) are accepted.
    """
    allowed, resolved, reason = _resolve_and_check(path)
    if not allowed:
        await params.result_callback({"path": path, "error": reason})
        return

    if not os.path.isfile(resolved):
        await params.result_callback({"path": path, "error": "not a regular file"})
        return

    try:
        size = os.path.getsize(resolved)
        with open(resolved, "rb") as f:
            content = f.read(_MAX_READ_BYTES)
    except OSError as e:
        await params.result_callback({"path": path, "error": f"read failed: {e}"})
        return

    # Decode utf-8 best-effort; binary files produce replacement chars but
    # the size info still tells the spoken summary what kind of file it is.
    text = content.decode("utf-8", errors="replace")
    await params.result_callback({
        "path": resolved,
        "size_bytes": size,
        "truncated": size > _MAX_READ_BYTES,
        "content": text,
    })


async def list_directory(params: FunctionCallParams, path: str) -> None:
    """List entries in a directory on the local filesystem.

    Returns names with type (file/dir/link) and size. Sorted by name,
    capped at 50 entries so the spoken summary can name the most relevant
    ones without listing everything.

    Args:
        path: Directory path. Relative paths resolve against $HOME. Only
            allowlisted roots accepted.
    """
    allowed, resolved, reason = _resolve_and_check(path)
    if not allowed:
        await params.result_callback({"path": path, "error": reason})
        return

    if not os.path.isdir(resolved):
        await params.result_callback({"path": path, "error": "not a directory"})
        return

    entries: list[dict[str, Any]] = []
    try:
        names = sorted(os.listdir(resolved))
    except OSError as e:
        await params.result_callback({"path": path, "error": f"listdir failed: {e}"})
        return

    truncated = False
    for name in names:
        if len(entries) >= _MAX_LIST_ENTRIES:
            truncated = True
            break
        full = os.path.join(resolved, name)
        try:
            st = os.lstat(full)
            if os.path.islink(full):
                kind = "link"
            elif os.path.isdir(full):
                kind = "dir"
            else:
                kind = "file"
            entries.append({"name": name, "type": kind, "size": st.st_size})
        except OSError:
            # Vanishing file between listdir and lstat — skip rather than fail
            continue

    await params.result_callback({
        "path": resolved,
        "entries": entries,
        "count": len(entries),
        "truncated": truncated,
    })


async def find_files(params: FunctionCallParams, pattern: str, root: str = "~/prj/intraface") -> None:
    """Find files whose path matches a pattern, recursively.

    Uses `rg --files` filtered through `grep -F pattern` for speed. Returns
    up to 50 matching paths (relative to root). For "where is X?" or "find
    all README files" type questions.

    Args:
        pattern: Substring to match against file paths (case-sensitive).
        root: Directory to search under. Defaults to ~/prj/intraface.
            Only allowlisted roots accepted.
    """
    allowed, resolved, reason = _resolve_and_check(root)
    if not allowed:
        await params.result_callback({"root": root, "error": reason})
        return

    if not os.path.isdir(resolved):
        await params.result_callback({"root": root, "error": "not a directory"})
        return

    # rg --files prints paths relative to its working dir. We pass the root
    # as the search path so paths come back relative to it. rg has no built-in
    # path-substring filter, so we filter in Python on the result list.
    ok, output = await _local(
        "rg", "--files", "--hidden", "-g", "!.git",
        resolved,
        timeout=8,
    )
    if not ok:
        await params.result_callback({"root": resolved, "error": output})
        return

    matches = [line for line in output.splitlines() if pattern in line]
    total = len(matches)
    truncated = total > _MAX_FIND_RESULTS
    matches = matches[:_MAX_FIND_RESULTS]

    await params.result_callback({
        "root": resolved,
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
        "truncated": truncated,
    })


async def grep_files(
    params: FunctionCallParams,
    pattern: str,
    root: str = "~/prj/intraface",
) -> None:
    """Search file contents for a pattern, recursively.

    Uses ripgrep (`rg`) for speed. Returns up to 20 matching lines with
    file path and line number. For "where is X defined?" or "find uses of Y".

    Args:
        pattern: Regex pattern to search for (ripgrep default syntax).
        root: Directory to search under. Defaults to ~/prj/intraface.
            Only allowlisted roots accepted.
    """
    allowed, resolved, reason = _resolve_and_check(root)
    if not allowed:
        await params.result_callback({"root": root, "error": reason})
        return

    if not os.path.isdir(resolved):
        await params.result_callback({"root": root, "error": "not a directory"})
        return

    # -n: line numbers, --no-heading: flat list (easier to summarize),
    # -m N: cap matches per file (ripgrep interprets -m as per-file cap).
    # Combined with our own 20-line cap for the whole result.
    ok, output = await _local(
        "rg", "-n", "--no-heading", "-m", "5",
        "--glob", "!.git",
        "--glob", "!*.lock",
        "--glob", "!*.bin",
        pattern,
        resolved,
        timeout=8,
    )
    # rg exits 1 when no matches, 2 on error. Treat 1 as empty success.
    if not ok and "exit 1" not in output and "exit" not in output:
        await params.result_callback({"root": resolved, "pattern": pattern, "error": output})
        return

    lines = output.splitlines() if ok else []
    total = len(lines)
    truncated = total > _MAX_GREP_MATCHES
    lines = lines[:_MAX_GREP_MATCHES]

    # Parse "path:line:content" into structured entries
    parsed: list[dict[str, Any]] = []
    for line in lines:
        # Split into at most 3 parts — content may contain colons
        parts = line.split(":", 2)
        if len(parts) == 3:
            parsed.append({"path": parts[0], "line": parts[1], "content": parts[2]})
        else:
            parsed.append({"raw": line})

    await params.result_callback({
        "root": resolved,
        "pattern": pattern,
        "matches": parsed,
        "count": len(parsed),
        "truncated": truncated,
    })


# ---------------------------------------------------------------------------
# Layer 3 — Web search
# ---------------------------------------------------------------------------

# SearXNG endpoint. Verified live 2026-07-29: sch.rtr.dev returns JSON,
# ~85ms TTFB, supports engine filters via ?engines=.
SEARXNG_URL = os.getenv("SEARXNG_URL", "https://sch.rtr.dev/search")

# Intent → engine recipes, ported from ~/.pi/agent/AGENTS.md.
# Adding a new intent is a one-line change here — the model gets the enum
# automatically via the web_search function signature.
SEARCH_INTENTS: dict[str, str] = {
    "general":  "",  # no filter — SearXNG picks engines
    "code":     "stackoverflow,github,superuser,askubuntu",
    "docs":     "mankier,mdn",
    "research": "arxiv,pubmed",
    "ml":       "huggingface",
}

# Cap on returned results. SearXNG often returns 30-50 even for weak matches;
# for voice we want only the strongest signals.
_MAX_SEARCH_RESULTS = 3
_SEARCH_TIMEOUT_SECS = 8


async def _http_get_json(url: str, timeout: int = _SEARCH_TIMEOUT_SECS) -> tuple[bool, Any]:
    """GET a URL and parse JSON. Returns (ok, data_or_error_string).

    Uses urllib rather than adding an aiohttp dependency — SearXNG responses
    are small (a few KB) and synchronous I/O in a thread is fine for the
    ~85-500ms calls we expect here.
    """
    try:
        # run_in_executor moves the blocking urllib call off the event loop
        loop = asyncio.get_running_loop()
        def _fetch():
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        body = await loop.run_in_executor(None, _fetch)
        return True, json.loads(body)
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"URL error: {e.reason}"
    except json.JSONDecodeError as e:
        return False, f"bad JSON: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def web_search(params: FunctionCallParams, query: str, intent: str = "general") -> None:
    """Search the web via the cluster's SearXNG instance at sch.rtr.dev.

    Returns the top 3 results with title, source domain, and a short snippet.
    Use for any question that can't be answered from the cluster or project
    files — library docs, current package versions, recent papers, code
    patterns, man pages.

    Args:
        query: The search query, URL-encoded automatically.
        intent: Search intent — picks the right engines. One of:
            general (default), code, docs, research, ml.
    """
    if intent not in SEARCH_INTENTS:
        await params.result_callback({
            "query": query,
            "error": f"unknown intent '{intent}'. valid: {list(SEARCH_INTENTS)}",
        })
        return

    engines = SEARCH_INTENTS[intent]
    qs = urllib.parse.urlencode({"q": query, "format": "json"})
    if engines:
        qs += "&engines=" + engines
    url = f"{SEARXNG_URL}?{qs}"

    ok, data = await _http_get_json(url)
    if not ok:
        await params.result_callback({"query": query, "intent": intent, "error": data})
        return

    raw_results = data.get("results", []) if isinstance(data, dict) else []
    if not raw_results:
        await params.result_callback({
            "query": query,
            "intent": intent,
            "results": [],
            "count": 0,
        })
        return

    # Shape each result for voice. We extract only the fields the spoken
    # summary needs: title, the registered domain (cleaner than full URL for
    # speech), and the snippet (capped at ~200 chars so one result can't
    # dominate the LLM context).
    shaped: list[dict[str, str]] = []
    for r in raw_results[:_MAX_SEARCH_RESULTS]:
        url_str = r.get("url", "")
        domain = _extract_domain(url_str)
        snippet = (r.get("content") or "").strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        shaped.append({
            "title": (r.get("title") or "").strip(),
            "source": domain,
            "snippet": snippet,
            "url": url_str,
        })

    await params.result_callback({
        "query": query,
        "intent": intent,
        "results": shaped,
        "count": len(shaped),
    })


def _extract_domain(url: str) -> str:
    """Pull the registered domain out of a URL for voice-friendly attribution.

    'https://docs.pipecat.ai/pipecat/learn/function-calling' → 'docs.pipecat.ai'
    'https://stackoverflow.com/q/123' → 'stackoverflow.com'
    Returns the raw string if it doesn't look like a URL (better to surface
    something odd than to drop the field).
    """
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc or url
    except ValueError:
        return url


ALL_TOOLS: tuple[Any, ...] = (
    # Layer 1 — cluster ops
    check_node, list_services, get_log_tail, get_port_state,
    # Layer 2 — filesystem (read-only)
    read_file, list_directory, find_files, grep_files,
    # Layer 3 — web search
    web_search,
)
