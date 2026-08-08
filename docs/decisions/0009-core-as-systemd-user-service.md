# 0009. Core is a managed systemd user service

Date: 2026-08-03
Status: accepted

Related: [0007](0007-explicit-per-node-runtime-deployment.md), [0008](0008-unit-cpu-runtime-mainstream-llama.md)

## Context

Through ADR 0008 the Core ran as a hand-launched `llama-server` process on
prtr. The PID was tracked in `~/.intraface/state/core-server.pid` and the
launch command lived in `engines.toml` as a comment, but the process had
no supervisor: a crash or reboot left prtr without a Core until someone
re-ran the command by hand.

ADR 0007 requires that runtime configuration identifies the actual
resident model, context window, endpoints, and node. A bare process with
a PID file does not satisfy that — the launch args were not in a
machine-readable runtime config, and there was no recovery contract.

The Unit side already had a managed runtime (ADR 0008's
`intraface-unit-server.service`). The Core was the inconsistency.

## Decision

The Core runs under a **systemd user service**,
`intraface-core.service`, with its runtime parameters in an
**env file** that the service sources.

```text
~/.config/systemd/user/intraface-core.service   # unit (stable, rarely edited)
~/.intraface/state/core-server.env              # runtime config (edited to swap)
```

The unit's `ExecStart` references the env-file variables (`${MODEL_PATH}`,
`${HOST}`, `${PORT}`, `${CTX}`, etc.) so the service file itself is
stable across model swaps. The env file is the single source of truth
for "which Core is resident."

**Linger is enabled** (`loginctl enable-linger prtr`) so the service
starts at boot without a login session.

### Swap procedure

```bash
# Edit the env file (typically just MODEL_PATH)
$EDITOR ~/.intraface/state/core-server.env
systemctl --user restart intraface-core
```

### Current resident (env file, 2026-08-03)

```text
MODEL_PATH=…/qwen3.6-35b-a3b-uncensored-aggressive/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf
HOST=127.0.0.1  PORT=7712  CTX=262144  NP=1  NGL=99  N_CPU_MOE=4
REASONING_FORMAT=deepseek
```

## Consequences

**Positive:**

- Core survives reboot and crash (Restart=on-failure, linger at boot).
- Runtime config satisfies ADR 0007: model, ctx, endpoint, node are all
  in one env file, not buried in a launch command or a PID file.
- Swap = edit env + restart, not "kill PID, find the command, re-run."
- Symmetric with the Unit server (both are `intraface-*-server.service`
  user units with env-file config).

**Negative:**

- User services require linger to start at boot; if linger is ever
  disabled, the Core will not come up without a login.
- The env file is outside this repo (under `~/.intraface/state/`), so a
  future agent must read the live file to know what is resident — the
  repo can only document the convention.

**Charter compatibility:**

- Test 5 (custody): the Core's runtime config is under
  `~/.intraface/state/`, consistent with Intraface-owned runtime state.
- ADR 0007 compliance: runtime config now explicitly identifies model,
  context window, endpoint, and node.

## References

- `~/.config/systemd/user/intraface-core.service` — the unit
- `~/.intraface/state/core-server.env` — runtime config (edit to swap)
- `engines.toml` → `[engines.ik_llama_cpp]` — the engine pin and binary
- `docs/core-model-baselines/` — verified profiles per candidate
