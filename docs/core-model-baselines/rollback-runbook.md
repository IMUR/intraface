# Core rollback runbook

How to restore the previous Core after a candidate swap. Written
2026-08-07 ahead of the Qwen3.6-27B Fable-Fusion-711 Q8 evaluation.

## Swap mechanics (how the Core is changed)

`intraface-core.service` (systemd user unit) is fully parameterized by
`/home/prtr/.intraface/state/core-server.env`. Swapping the Core = edit
`MODEL_PATH` (and tuning vars) in that file, then:

```sh
systemctl --user restart intraface-core
```

No other state changes. The service unit itself
(`~/.config/systemd/user/intraface-core.service`) only needs editing if
the candidate requires flags the env file cannot express (e.g.
`-ctk/-ctv` KV-cache quantization, `--mmproj` for vision).

## Known-good state (snapshot 2026-08-07)

Verified against the live process (PID 43771, running since 2026-08-03):

- **Resident model:** Qwen3.6-35B-A3B Uncensored Aggressive **Q6_K_P**
  - `/home/prtr/.intraface/models/core/qwen3.6-35b-a3b-uncensored-aggressive/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf`
  - Confirmed still on disk at snapshot time.
- **Env backup:** `~/.intraface/state/core-server.env.known-good-2026-08-07`
  (byte-identical copy of the live env file)

Known-good env contents:

```ini
MODEL_PATH=/home/prtr/.intraface/models/core/qwen3.6-35b-a3b-uncensored-aggressive/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf
HOST=127.0.0.1
PORT=7712
CTX=262144
NP=1
NGL=99
N_CPU_MOE=4
REASONING_FORMAT=deepseek
```

## Rollback procedure

```sh
# 1. Restore the known-good env
cp -a ~/.intraface/state/core-server.env.known-good-2026-08-07 \
      ~/.intraface/state/core-server.env

# 2. Restart the Core
systemctl --user restart intraface-core

# 3. Verify (arch, context, and slot should come up clean)
sleep 20
journalctl --user -u intraface-core -n 50 --no-pager
curl -s http://127.0.0.1:7712/health
curl -s http://127.0.0.1:7712/v1/models
```

Expected: health OK, model id matching the Q6_K_P file, ctx 262144.

## If the service unit was also edited

Only needed when the candidate required extra flags:

```sh
systemctl --user edit --full intraface-core.service   # remove added flags
systemctl --user daemon-reload
systemctl --user restart intraface-core
```

The unit's canonical form is the parameterized ExecStart recorded in
`engines.toml`; any extra flags should be considered evaluation-local
and removed on rollback.

## Notes for the FF711 Q8 candidate

- The 27B is **dense** — set `N_CPU_MOE=0` for it (the `4` is MoE
  offloading for the A3B; harmless-but-meaningless on a dense model).
- If evaluating the MTP quant or vision (`--mmproj`), the unit needs
  extra flags — see "If the service unit was also edited" above before
  rolling back.
- Do not delete the Q6_K_P GGUF until the evaluation concludes; it is
  the rollback target.
