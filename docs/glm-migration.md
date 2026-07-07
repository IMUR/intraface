# GLM-4.7-Flash migration into Intraface custody

**Status:** not started. This document captures the implications of moving
the live Core model into `~/.intraface/models/core/` custody so the
decision can be made with full information.

**Priority:** high follow-up (per session 2026-07-07).

---

## Current state (verified 2026-07-07)

| What | Value |
|---|---|
| Model file | `zai-org_GLM-4.7-Flash-Q8_0.gguf` |
| Current location | `/home/prtr/models/glm-4.7-flash/` |
| Size | 31.8 GB (31,842,799,488 bytes) |
| Process | `llama-server` (ik_llama.cpp), PID 634777 |
| Listen | `127.0.0.1:7712` |
| State | Sleeping, ~95% VRAM |
| Launched by | **Manual** (no systemd unit, no service definition exists) |
| Cwd | `/home/prtr/prj/ik_llama.cpp` |
| Binary | `./build/bin/llama-server` (relative to cwd) |

Full launch line (from `/proc/634777/cmdline`):

```
./build/bin/llama-server
  -m /home/prtr/models/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf
  --host 127.0.0.1 --port 7712
  -c 98304 -np 1 -ngl 99 --n-cpu-moe 4 -cram 0 --ctx-checkpoints 0 --jinja
```

## Target state

```
~/.intraface/models/core/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf
```

(`core/glm-4.7-flash/` created in same shape as
`unit/lfm2.5-1.2b-instruct/` — one subdir per model identity, so a future
candidate or rollback can coexist on disk.)

## Migration steps

In order. Each step has a check.

1. **Capture current launch line** (above) into a script so it can be
   reproduced. **Check:** script saved at, e.g., `~/.intraface/bin/start-glm.sh`.

2. **Pick a maintenance window.** Anyone actively using `127.0.0.1:7712`
   (Pi at minimum, possibly other agents) will see connection failures
   during the swap. Announce or do during low-use hours.

3. **Pre-create the target directory:**
   `mkdir -p ~/.intraface/models/core/glm-4.7-flash/`

4. **Stop the running service:** `kill 634777` (SIGTERM first; SIGKILL
   only if it doesn't exit cleanly within ~30s).
   **Check:** `ss -tlnp | grep 7712` returns nothing;
   `/proc/634777` does not exist.

5. **Move the file:** `mv /home/prtr/models/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf ~/.intraface/models/core/glm-4.7-flash/`
   Same filesystem (`/dev/nvme0n1p2`) — atomic rename, no copy time.

6. **Clean up the now-empty source directory:**
   `rmdir /home/prtr/models/glm-4.7-flash && rmdir /home/prtr/models`
   (only if both are empty after the move).

7. **Restart with the captured launch line, repointed:**
   `cd ~/prj/ik_llama.cpp && ./build/bin/llama-server -m ~/.intraface/models/core/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf --host 127.0.0.1 --port 7712 -c 98304 -np 1 -ngl 99 --n-cpu-moe 4 -cram 0 --ctx-checkpoints 0 --jinja`

8. **Verify health:**
   - `ss -tlnp | grep 7712` shows `llama-server` listening.
   - `curl -s http://127.0.0.1:7712/health` (or whatever the ik_llama
     health endpoint is) returns OK.
   - A trivial completion request returns in expected latency.

9. **Update this doc + `~/.intraface/models/core/README.md`** to reflect
   "moved on <date>".

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Service downtime.** GLM is the orchestrator Core; killing it interrupts any active Pi/agent session depending on it. | Schedule a maintenance window. Pre-warn in any active agent sessions. |
| **Model fails to reload after move** (e.g. mmap state, GPU not cleanly released by old process). | Verify process is fully dead (`/proc/<pid>` gone, `nvidia-smi` shows VRAM freed) before restart. |
| **Launch line drift.** If the captured cmdline is incomplete or the binary has been rebuilt since first launch, the restart may behave differently. | Capture the *exact* cmdline at the moment of kill (re-read `/proc/634777/cmdline` immediately before, not from this doc). |
| **Disk space transient.** None expected — `mv` is rename on same FS, no copy. | N/A. |
| **The 31.8 GB file is the only copy.** No git, no Forgejo (gitignored by policy). | Pre-check `stat` size matches before deleting source; consider a one-time checksum. |
| **Other systems have hardcoded `/home/prtr/models/...` paths.** Unknown without audit. | `rg -l '/home/prtr/models/glm-4.7-flash' ~/` before migration. |

## What this migration does *not* include

- **systemd unit for GLM.** Currently it's manually launched. A service
  unit is a separate decision (would also solve the "auto-restart on
  crash" question).
- **Wrapping the launch in a `~/.intraface/bin/start-glm.sh` script.**
  Step 1 mentions this; it's a useful artifact but optional.
- **Moving the engine binary.** `llama-server` stays at
  `~/prj/ik_llama.cpp/build/bin/llama-server`. Binary deployment to
  `~/.intraface/bin/` is a separate task.

## Open question to settle before migration

- **Audit for hardcoded paths first.** Before step 1, run
  `rg -l '/home/prtr/models/glm' ~/` and review hits. The launch line
  *itself* is one such hardcoded path; there may be others (scripts,
  Pi extension configs, notes).

- **Manual launch vs systemd.** Migration is a natural moment to ask
  whether GLM should get a systemd unit. Out of scope for this doc, but
  worth flagging for the next decision.
