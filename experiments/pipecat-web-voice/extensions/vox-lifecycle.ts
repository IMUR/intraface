/**
 * vox-lifecycle — Observational extension for Vox-delegated Pi subprocesses.
 *
 * Emits structured JSONL lifecycle events to stderr so the supervising Vox
 * process can track Pi invocation progress without polluting stdout (which
 * carries the final model response).
 *
 * INVARIANTS:
 * - Registers NO model-callable tools.
 * - Performs NO filesystem mutation.
 * - Performs NO network I/O.
 * - Reads only process.env (VOX_DELEGATION_ID, PI_SESSION_ID).
 * - Writes only to process.stderr (one JSON object per line).
 * - Event handlers are try/catch wrapped so a single handler failure does
 *   not prevent Pi from returning its final response (fail-open).
 *
 * USAGE:
 *   pi --print --no-tools --no-extensions --no-context-files \
 *      --no-skills --no-prompt-templates \
 *      --extension /path/to/vox-lifecycle.ts \
 *      --session-id <id> --session-dir <dir> \
 *      --system-prompt "..." \
 *      "task text"
 *
 * ENV:
 *   VOX_DELEGATION_ID — per-delegation correlation ID (unique per tool call).
 *     Falls back to "unknown" if unset. The supervising Vox process sets this
 *     to a fresh UUID for each delegate_to_pi invocation so that concurrent
 *     or retried delegations can be distinguished on a shared stderr stream.
 *
 * STDERR PROTOCOL (JSONL, one object per line):
 *
 *   { "d": "<delegation-id>", "s": <sequence>, "t": "started",   "mode": "print", "pid": <int> }
 *   { "d": "<delegation-id>", "s": <sequence>, "t": "processing" }
 *   { "d": "<delegation-id>", "s": <sequence>, "t": "completed" }
 *   { "d": "<delegation-id>", "s": <sequence>, "t": "shutdown" }
 *
 *   Fields:
 *     d  — delegation correlation ID (matches VOX_DELEGATION_ID)
 *     s  — monotonically increasing sequence number within this invocation
 *     t  — event type: started | processing | completed | shutdown
 *     mode — only on "started": the Pi run mode (always "print" for Vox)
 *     pid — only on "started": the Pi process PID
 *
 *   Non-JSON lines on stderr (Pi's own warnings, extension error logs) are
 *   ignored by the Vox parser — they do not start with "{".
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function emit(seq: number, type: string, extra?: Record<string, unknown>): void {
  try {
    const event: Record<string, unknown> = {
      d: process.env.VOX_DELEGATION_ID ?? "unknown",
      s: seq,
      t: type,
    };
    if (extra) {
      Object.assign(event, extra);
    }
    process.stderr.write(JSON.stringify(event) + "\n");
  } catch {
    // Fail silently — do not let a logging error break Pi's response path.
  }
}

export default function (_pi: ExtensionAPI): void {
  let seq = 0;

  _pi.on("session_start", async (_event, ctx) => {
    try {
      emit(seq++, "started", { mode: ctx.mode, pid: process.pid });
    } catch {
      // Swallow — Pi catches event handler errors and logs them,
      // but we add a second layer of defense.
    }
  });

  _pi.on("agent_start", async (_event, _ctx) => {
    try {
      emit(seq++, "processing");
    } catch {
      // Swallow.
    }
  });

  _pi.on("agent_settled", async (_event, _ctx) => {
    try {
      emit(seq++, "completed");
    } catch {
      // Swallow.
    }
  });

  _pi.on("session_shutdown", async (_event, _ctx) => {
    try {
      emit(seq++, "shutdown");
    } catch {
      // Swallow.
    }
  });
}
