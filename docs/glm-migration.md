# GLM-4.7-Flash migration into Intraface custody

**Status:** not started. **Priority:** high follow-up.

This is a **runbook**, not a decision record. The custody decision itself
lives in `docs/decisions/0001-core-unit-model-custody.md`; the target path
and Core/Unit rationale live in `~/.intraface/models/core/README.md`. This
document captures the operational procedure, risks, and open questions for
the actual migration.

---

## Current state (verified 2026-07-07)

| What | Value |
|---|---|
| Model file | `zai-org_GLM-4.7-Flash-Q8_0.gguf` |
| Current location | `/home/prtr/models/glm-4.7-flash/` |
| Size | 31.8 GB (31,842,799,488 bytes) |
| Process | `llama-server` (ik_llama.cpp), PID 634777 |
| Listen | `127.0.0.1:7712` |
| Launched by | **Manual** (no systemd unit exists; will not survive reboot) |
| Cwd | `/home/prtr/prj/ik_llama.cpp` |
| Binary | `./build/bin/llama-server` (relative to cwd) |

**Re-read `/proc/<pid>/cmdline` immediately before kill** — the line below
is from 2026-07-07 and may have drifted if the service was restarted.

```
./build/bin/llama-server
  -m /home/prtr/models/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf
  --host 127.0.0.1 --port 7712
  -c 98304 -np 1 -ngl 99 --n-cpu-moe 4 -cram 0 --ctx-checkpoints 0 --jinja
```

## Pre-migration audit

Before step 1, find every reference to the old path so nothing silently
breaks when the file moves:

```bash
rg -l '/home/prtr/models/glm' ~/ 2>/dev/null
```

Known references today: the launch line itself, this doc, the
`~/.intraface/models/core/README.md`. Unknown references are what the audit
is for.

## Migration procedure

1. **Capture the current launch line** fresh from `/proc/634777/cmdline`
   (decode with `tr '\0' ' '`). Save as `~/.intraface/bin/start-glm.sh`
   with the path repointed to the new location (or, if step 8 below is
   done, to a systemd unit).

2. **Pick a maintenance window.** Anyone using `127.0.0.1:7712` (Pi at
   minimum, possibly other agents) sees connection failures during the
   swap.

3. **Pre-create the target directory:**
   `mkdir -p ~/.intraface/models/core/glm-4.7-flash/`

4. **Stop the running service:** `kill 634777` (SIGTERM; SIGKILL after
   ~30s if it doesn't exit). Verify with `ss -tlnp | grep 7712` (empty)
   and `/proc/634777` (gone). `nvidia-smi` should show VRAM freed.

5. **Move the file:**
   `mv /home/prtr/models/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf ~/.intraface/models/core/glm-4.7-flash/`
   Same filesystem (`/dev/nvme0n1p2`) — atomic rename.

6. **Clean up the now-empty source:**
   `rmdir /home/prtr/models/glm-4.7-flash && rmdir /home/prtr/models`
   (only if both empty).

7. **Restart with the captured launch line, repointed.** Verify:
   - `ss -tlnp | grep 7712` shows `llama-server` listening.
   - A trivial completion request returns expected latency.

8. **Update this doc + `~/.intraface/models/core/README.md`** to
   "moved on \<date\>".

## Risks

| Risk | Mitigation |
|---|---|
| Service downtime interrupts active Pi/agent sessions. | Maintenance window; pre-warn. |
| Old process doesn't cleanly release VRAM. | Verify `/proc/<pid>` gone + `nvidia-smi` before restart. |
| Launch line drift since capture. | Re-read cmdline immediately before kill. |
| 31.8 GB file is the only copy (no git, no Forgejo). | Pre-check `stat` size; optional checksum. |
| Unknown hardcoded paths break silently. | Pre-migration audit (above). |

## Open question: systemd unit?

GLM is currently manually launched and won't survive reboot. Migration is
the natural moment to decide whether to wrap it in a systemd unit for
auto-restart on crash and start-on-boot. **Out of scope for this runbook**;
separate decision.

## What this migration does *not* include

- **Engine binary deployment.** `llama-server` stays at
  `~/prj/ik_llama.cpp/build/bin/llama-server`. Binary install to
  `~/.intraface/bin/` is a separate task (see ADR 0002).
- **systemd unit.** See open question above.
