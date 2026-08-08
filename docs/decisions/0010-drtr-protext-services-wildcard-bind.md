# 0010. drtr Protext llama services bound 0.0.0.0

Date: 2026-08-01
Status: accepted

Related: [0007](0007-explicit-per-node-runtime-deployment.md)

## Context

The Protext llama services on drtr (`llama-embed`, `llama-vl`,
`llama-extract`, `llama-summarize` on ports 7755, 7764, 7765, 7766)
were bound to `127.0.0.1` — loopback only. The unit files even carried
the comment "Loopback only. No Tailscale / external exposure."

That forced cross-node consumers onto SSH tunnels. Vice's memory
pipeline (`vice-memory-tunnel.service` on prtr) maintained a persistent
`ssh -L` forward of `17755` → drtr:7755 and `17765` → drtr:7765 just to
reach embed and extract. This works but adds a per-client process, a
failure mode (tunnel drops, restart loop), and a port-numbering scheme
that differs per client.

The voice services on the same host (Parakeet `:7733`, Chatterbox
`:7744`) and SurrealDB (`:6600`) were already reachable across the
cluster. Only the Protext llama stack was loopback-locked.

Cluster convention (DECISIONS 0006, recorded in the rtr profile) favors
loopback-only for service daemons. Rebinding to `0.0.0.0` is a
deliberate divergence from that convention for this specific stack.

## Decision

Rebind the four Protext llama services from `127.0.0.1` to `0.0.0.0`:

```text
llama-embed     7755   127.0.0.1 → 0.0.0.0
llama-vl        7764   127.0.0.1 → 0.0.0.0
llama-extract   7765   127.0.0.1 → 0.0.0.0
llama-summarize 7766   127.0.0.1 → 0.0.0.0
```

Applied by editing `/etc/systemd/system/llama-*.service` on drtr
(`--host 127.0.0.1` → `--host 0.0.0.0`), daemon-reload, restart.

Backups of the pre-change unit files are on drtr at
`/etc/systemd/system/llama-*.service.bak-2026-08-01-loopback`.

### Reachability after change

From any cluster node, via tailnet or LAN:

```text
http://d.rtr.rtr.dev:7755   # embed (bge-m3)
http://d.rtr.rtr.dev:7764   # vl (LFM2.5-VL-1.6B)
http://d.rtr.rtr.dev:7765   # extract (LFM2-1.2B-Extract)
http://d.rtr.rtr.dev:7766   # summarize (LFM2-2.6B-Transcript)
```

Or by IP: `100.64.0.3:7755` (tailnet), `192.168.254.33:7755` (LAN).

## Consequences

**Positive:**

- Cross-node consumers (Vice, future Intraface Units, Protext clients)
  reach the Protext llama stack directly — no SSH tunnel per client.
- One mental model for all of drtr's AI surface (voice + NLP + DB all
  cluster-reachable), not two.
- Vice's `vice-memory-tunnel.service` is now redundant and can be
  retired once Vice is repointed at `d.rtr.rtr.dev:7755/:7765`.

**Negative:**

- These endpoints have **no auth**. `0.0.0.0` exposes them on the LAN
  (`192.168.254.0/24`), not just the tailnet. Acceptable on a
  single-user home LAN; would not be acceptable on a shared network.
- Diverges from the cluster's loopback convention (DECISIONS 0006).
  This divergence is intentional and scoped to drtr's AI-port block,
  not a cluster-wide policy change.
- Tailscale ACLs are not in use; any tailnet peer can reach these ports.

## Follow-up

- **Retire `vice-memory-tunnel.service`** on prtr once Vice points at
  `d.rtr.rtr.dev` directly. The tunnel is still active as of
  2026-08-03; it forwards `17755`/`17765` but is no longer the only
  path.
- **Update the rtr profile** (drtr section) to reflect the new binds
  and drop the "loopback only" note. The profile lives outside this
  repo; this ADR is the intraface-side record.

## References

- `/etc/systemd/system/llama-{embed,vl,extract,summarize}.service` on drtr
- `.bak-2026-08-01-loopback` backups on drtr (pre-change unit files)
- `~/.config/systemd/user/vice-memory-tunnel.service` on prtr (now redundant)
