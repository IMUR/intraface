---
title: "Reactor `rtr` Cluster Reference"
date: 2026-04-01
verified: 2026-07-17
---

# Reactor `rtr` Cluster Reference

Steady-state reference for the rtr cluster. Verified against live state 2026-07-17 via SSH probes from crtr (see `rtr-profile-audit.md` for the audit trail). For change history or in-progress work, see `REBUILD.md` at the repo root.

## Nodes

| Node | OS hostname | Tailnet name | Tailnet IPv4 | LAN IP | Arch | OS | Role |
|------|-------------|--------------|--------------|--------|------|----|-----|
| Projector | `projector` | `p` | `100.64.0.2` | `192.168.254.22` | x86_64 | Debian 13 (trixie) | Compute, AI inference |
| Cooperator | `cooperator` | `c` | `100.64.0.4` | `192.168.254.11` | arm64 | Debian 13 (trixie) | Edge ingress, Headscale host, Caddy gateway, cluster ops |
| Director | `director` | `d` | `100.64.0.3` | `192.168.254.33` | x86_64 | Debian 13 (trixie) | GPU inference, voice pipeline |
| Terminator | `terminator` | `t` | `100.64.0.1` | `192.168.254.107` | arm64 | macOS 26.5 | Workstation, cluster entry-point |

**Tailnet:** single user `rtr`, MagicDNS base `rtr.rtr.dev`. Nodes resolve as `<letter>.rtr.rtr.dev` via MagicDNS only (not public DNS — see Namespace Policy below). See `docs/tailnet.md` for the full tailnet reference.

**Gateway vIP:** `192.168.254.10/24` is a VRRP virtual IP managed by keepalived. `crtr` holds it at priority 150 (MASTER); `prtr` takes over at priority 100 (BACKUP); `drtr` is also a peer at priority 50 (BACKUP).

## Namespace Policy

Structurally enforced via DNS level separation (DECISIONS 0008):

| Namespace | Resolution | Reserved for |
|-----------|------------|--------------|
| `<a-z>.rtr.rtr.dev` (two-level) | MagicDNS only | Tailnet nodes — single-letter names |
| `<multi-letter>.rtr.dev` (single-label) | Public DNS (GoDaddy wildcard A) | Services behind Caddy |
| `rtr.dev` (apex) | Public DNS | Personal homepage |
| `vpn.rtr.dev` | Public DNS + MagicDNS forward | Headscale control plane (reserved) |

The GoDaddy wildcard `*.rtr.dev` covers single-label subdomains only; per RFC 4592 it does not match `c.rtr.rtr.dev`. So tailnet node names are unresolvable from public DNS — tailnet-only by construction. A node and a service cannot collide.

## Hardware

### Projector (`prtr`)

- **CPU:** Intel Core i9-9900X, 10 cores / 20 threads @ 3.50 GHz
- **GPU:** 2× NVIDIA GeForce RTX 3090 (water-cooled, EK Vector RTX blocks; 350 W TDP each; driver `550.163.01`, CUDA runtime 12.4)
- **RAM:** 125 GiB DDR4 (mixed Corsair kits, 8 DIMM slots populated, operating at 2400 MT/s)
- **Disk:** 889 GiB root (423 GiB used, 51%)
- **Motherboard:** ASUSTeK PRIME X299-DELUXE II (Intel X299 chipset)

### Cooperator (`crtr`)

- **CPU:** BCM2712, 4 cores @ 2.40 GHz (Raspberry Pi 5)
- **RAM:** 16 GiB
- **Disk:** 941 GiB SD card at `/dev/mmcblk0p2` (11 GiB used, SD-card boot)
- **Accelerator:** AI HAT+ 2 (Hailo-10H) at `0001:01:00.0` — present, not yet configured

### Director (`drtr`)

- **CPU:** Intel Core i9-9900K, 16 threads @ 3.60 GHz base (5.00 GHz turbo)
- **GPU:** NVIDIA GeForce RTX 2080 (driver `550.163.01`)
- **RAM:** 62 GiB
- **Disk:** 889 GiB root (250 GiB used, 30%)

### Terminator (`trtr`)

- **CPU:** Apple M4, 10 cores (4 Performance + 6 Efficiency)
- **GPU:** M4 integrated, 10 cores
- **RAM:** 24 GiB
- **Disk:** 460 GiB APFS
- **OS:** macOS 26.5.2 (Build 25F84), Darwin 25.5.0

## Port Block Model

| Block | Range | Category | Use |
|------|-------|----------|-----|
| Daemon | `44`** | Engine | Service daemons, gateways, protocol surfaces |
| WebUI | `55`** | Access | Browser-facing UIs, consoles, panels |
| Data | `66`** | Storage | Stores, caches, queues, indexes |
| AI | `77`** | Thought | LLM, STT, TTS, embeddings, model serving |

---

## Projector (`prtr`) — Verified 2026-07-17

| Port | Bind | Service | Unit / Process | Status |
|------|------|---------|----------------|--------|
| `5511` | `127.0.0.1` | XTDB v2.1.0 (pgwire) | java | ✅ Live |
| `6379` | `127.0.0.1` | Redis | `redis-server` | ✅ Live |
| `7711` | `*` | Ollama (2× RTX 3090) | `ollama.service` | ✅ Live |
| `7712` | `127.0.0.1` | llama-server | `llama-server` | ✅ Live (not in prior profile) |
| `9999` | `127.0.0.1` | python3 (unidentified) | python3 | ✅ Live (not in prior profile) |
| `4096` | `127.0.0.1` | kilo (code-server variant) | kilo | ✅ Live (not in prior profile) |
| `<ephemeral>` | `127.0.0.1` | multiple node processes | node | ✅ Live (dev/work tools) |

**Retired since prior profile:** `4444` (OpenClaw gateway), `4477` (OpenFang agent runtime). Both units inactive.

**Bind policy note:** Ollama (`*:7711`) binds all interfaces — pre-existing, pre-dates DECISIONS 0006's loopback-only convention. (Cockpit previously bound `*:9090` on prtr/drtr but was purged 2026-07-17 — wildcard bind was a separate violation of DECISIONS 0006, now resolved by removal.)

---

## Cooperator (`crtr`) — Verified 2026-07-17

### Native Services

| Port | Bind | Service | Unit | Status |
|------|------|---------|------|--------|
| `22` | `0.0.0.0` + `[::]` | SSH | `ssh.service` | ✅ Live |
| `80` | `192.168.254.10` | Caddy HTTP (redirect to HTTPS) | `caddy.service` | ✅ Live |
| `443` | `192.168.254.10` | Caddy HTTPS (reverse proxy) | `caddy.service` | ✅ Live |
| `2019` | `127.0.0.1` | Caddy admin API | `caddy.service` | ✅ Live |
| `4422` | `127.0.0.1` | Headscale control plane | `headscale.service` | ✅ Live |
| `9090` | `127.0.0.1` | Headscale metrics | `headscale.service` | ✅ Live |
| — | — | keepalived (VRRP vIP) | `keepalived.service` | ✅ Live |
| — | — | tailscaled (tailnet peer) | `tailscaled.service` | ✅ Live |

**Retired since prior profile (everything else):** Pi-hole DNS (53), Mosquitto MQTT (1883), Suggestion Box (3010), KVM Console (4400), Forgejo web/API (4466), SRH Next.js (4488), SearXNG (5588), Redis (6379), Forgejo SSH/git (6666), Hailo-Ollama (7788), Pi-hole web UI (8080), Atuin server (8811), Cockpit.

### Docker Services

**None.** Docker is not installed on crtr (`bash: command not found: docker`). All prior containers (Homepage, Grafana, Loki, eMCP, Headplane, n8n, Infisical, OpenWebUI, cAdvisor, Termix, Home Assistant, Jupyter, Portainer, Prometheus, node-exporter, blackbox-exporter, Lightpanda, Pi-hole exporter) are gone. For redeployment plans see `REBUILD.md`.

### Caddyfile

The Caddyfile at `/etc/caddy/Caddyfile` (640 root:caddy) contains embedded operational guidance: DNS-01 procedure, DNS-provider migration runbook, instructions for adding new services. It is the canonical "how to add a service" reference for the cluster.

---

## Director (`drtr`) — Verified 2026-07-17

| Port | Bind | Service | Unit | Status |
|------|------|---------|------|--------|
| `6600` | `0.0.0.0` | SurrealDB v3.1.4 | `protext.service` | ✅ Live |
| `7733` | `0.0.0.0` | Parakeet TDT 0.6B STT (RTX 2080) | `parakeet-stt.service` | ✅ Live |
| `7744` | `0.0.0.0` | Chatterbox-Turbo TTS (RTX 2080) | `chatterbox-tts.service` | ✅ Live |
| `7755` | `127.0.0.1` | llama-embed (bge-m3 Q8_0) | `llama-embed.service` | ✅ Live |
| `7756` | `127.0.0.1` | protext-rerank-mini6 | `protext-rerank-mini6.service` | ✅ Live |
| `7757` | `127.0.0.1` | protext-pca | `protext-pca.service` | ✅ Live |
| `7758` | `127.0.0.1` | protext-extractive-kmeans | `protext-extractive-kmeans.service` | ✅ Live |
| `7759` | `127.0.0.1` | protext-utility-gbr | `protext-utility-gbr.service` | ✅ Live |
| `7764` | `127.0.0.1` | llama-vl (LFM2.5-VL-1.6B Q8_0) | `llama-vl.service` | ✅ Live |
| `7765` | `127.0.0.1` | llama-extract (LFM2-1.2B-Extract Q8_0) | `llama-extract.service` | ✅ Live |
| `7766` | `127.0.0.1` | llama-summarize (LFM2-2.6B-Transcript Q8_0) | `llama-summarize.service` | ✅ Live |
| `7799` | `*` | bun (unidentified) | bun | ✅ Live (not in prior profile) |
| `9001` | `0.0.0.0` | Docker portainer-agent | docker | ✅ Live |
| `111` | `0.0.0.0` | rpcbind (NFS portmapper) | rpcbind | ⚠️ Live — security-flagged (unusual on a GPU box) |

**RTX 2080:** Chatterbox ~3.2 GB + Parakeet ~1.4 GB ≈ 4.6 GB / 8 GB.

**Docker on drtr:** running, single container (`portainer_agent`, up 2+ weeks). No other containers.

**Bind policy note:** 6600, 7733, 7744, 9001, 9090, 111 bind `0.0.0.0` or `*` — pre-existing, pre-dates DECISIONS 0006.

---

## Caddy Reverse Proxy Domains (crtr)

All domains served via Caddy on crtr, bound to the vIP `192.168.254.10`. TLS via DNS-01 with wildcard certs for `*.ism.la` and `*.rtr.dev`.

### Active

| Domain | Target | Service |
|--------|--------|---------|
| `vpn.rtr.dev` | `127.0.0.1:4422` | Headscale control plane |

### Placeholder / 503

| Domain | Notes |
|--------|-------|
| `vpn.ism.la` | Explicit 503 placeholder ("Headplane not yet deployed") |
| All other `*.ism.la` | Default 503 "Not configured" |
| All other `*.rtr.dev` | Default 503 "Not configured" |

The prior installed base of `*.ism.la` services (Forgejo, Pi-hole, Grafana, n8n, OpenWebUI, Infisical, Home Assistant, Jupyter, Portainer, Prometheus, Termix, KVM Console, SearXNG, SRH, Suggestion Box, eMCP, OpenClaw, OpenFang, Headplane) is **not currently deployed**. TLS still serves (certs valid), but no backends are wired. See `REBUILD.md` for redeployment plans.

Pending decision: whether to migrate `*.ism.la` backends to `*.rtr.dev` when redeployed, or keep both zones.

---

## Shared Storage

**Not currently available.** Samba is gone from crtr; `/mnt/ops` does not exist on any node. Prior setup (`/var/lib/ops.img` loopback on crtr, Samba-served to peers) was lost in the 2026-07-11 rebuild and is intentionally not being recreated as single-host SMB.

**Plan:** GlusterFS (or equivalent replicated storage) across crtr/prtr/drtr. See `REBUILD.md` future-workstreams.

**Latent bug:** drtr's `/etc/fstab` still has an `/mnt/ops` entry pointing at `//100.64.0.1/ops` — that IP is now trtr, not crtr. Mount attempt fails with "Host is down." Needs cleanup when storage is re-established.

---

## SSH Access

Harmonized 2026-07-17 (see `REBUILD.md` for verification citation). All four nodes have the same alias pattern.

### Tailnet aliases (work from any node, full mesh)

| Alias | HostName | User | IdentityFile |
|-------|----------|------|--------------|
| `c` | `100.64.0.4` | `crtr` | `~/.ssh/id_ed25519` |
| `p` | `100.64.0.2` | `prtr` | `~/.ssh/id_ed25519` |
| `d` | `100.64.0.3` | `drtr` | `~/.ssh/id_ed25519` |
| `t` | `100.64.0.1` | `trtr` | `~/.ssh/id_ed25519` |

### LAN aliases (fallback when tailnet is unavailable)

| Alias | HostName | User | IdentityFile |
|-------|----------|------|--------------|
| `crtr` | `192.168.254.11` | `crtr` | `~/.ssh/id_ed25519_self` (self) |
| `prtr` | `192.168.254.22` | `prtr` | `~/.ssh/id_ed25519_self` (self) |
| `drtr` | `192.168.254.33` | `drtr` | `~/.ssh/id_ed25519_self` (self) |
| `trtr` | `192.168.254.107` | `trtr` | `~/.ssh/id_ed25519` |
| `admin` | `192.168.254.254` | `admin` | `~/.ssh/id_ed25519` (router) |

### Defaults (Host *)

All nodes: `SetEnv TERM=xterm-256color`, `ServerAliveInterval 60`, `ServerAliveCountMax 3`, `ControlMaster auto`, `ControlPath ~/.ssh/sockets/%r@%h:%p`, `ControlPersist 10m`.

### Key layout

Each node has `id_ed25519` (cluster identity) + `id_ed25519_self` (self-SSH). `authorized_keys` on each node contains the cluster keys of all four nodes (incl. own — added/fixed 2026-07-17).

### Forgejo SSH

`Host git.ism.la` blocks still exist in some node configs at port 6666, but Forgejo is not currently deployed. The config is inert.

### Stale alias blocks (deferred cleanup)

Aliases for absent nodes (`zrtr`, `kali`, `irtr`, `wrtr`, `pi`) still present on prtr/drtr/trtr configs. Tracked for cleanup in `REBUILD.md`.

### Chezmoi

prtr/drtr configs carry `# Managed by chezmoi` header; chezmoi source on `/mnt/ops/dotfiles` is not currently mounted. Hand-edits accepted for the tailnet block; reconciliation deferred.

---

## Toolchain

All runtime versions managed by `mise`; dotfiles by `chezmoi` (source on `/mnt/ops/dotfiles`, not currently mounted).

### Python

| Node | Version | Resolves to | Via |
|------|---------|-------------|-----|
| `crtr` | 3.14.5 | `~/.local/share/mise/installs/python/3.14.5/bin/python3` | mise |
| `prtr` | 3.14.5 | `~/.local/share/mise/installs/python/3.14.5/bin/python3` | mise |
| `drtr` | 3.14.5 | `~/.local/share/mise/installs/python/3.14.5/bin/python3` | mise |
| `trtr` | **3.14.3** (drift) | `~/.local/share/mise/shims/python3` | mise |

Use `uv` for installs/envs and `uvx` for one-offs (per AGENTS.md).

### mise versions (cluster drift)

| Node | Version |
|------|---------|
| `crtr` | `2026.7.5 linux-arm64` |
| `prtr` | `2026.5.16 linux-x64` |
| `drtr` | `2026.5.16 linux-x64` |
| `trtr` | `2026.3.9 macos-arm64` |

Versions not uniform. Alignment tracked separately.

### JavaScript

`bun` + `node 24` via `mise`. Use `bun run` / `bunx` in place of `npm run` / `npx`.

### Shells

| Node | Login shell | Notes |
|------|-------------|-------|
| `crtr` | `/bin/bash` | zsh installed; bash is login shell |
| `prtr` | `/bin/bash` | zsh installed; bash is login shell |
| `drtr` | `/bin/bash` | zsh installed; bash is login shell |
| `trtr` | `/bin/zsh` | zsh is login shell |

Per AGENTS.md: **bash is the default login shell for cluster ops.** Bare `ssh <node> '<cmd>'` works via `.bashrc → .profile`. zsh is for interactive use only. **Do not use `zsh -l -c` for non-interactive cluster ops** — it's unnecessary on the Linux nodes (which use bash) and unreliable as a general pattern.

### Shell Environment

chezmoi owns `.zshrc`, `.profile`, `.bashrc`, and `.zshenv` where configured. Direct edits to those files will be clobbered on the next `chezmoi update --force`. Node-specific overrides belong in:

| File | Sourced by | Present on |
|------|-----------|------------|
| `~/.zshrc.local` | `.zshrc` | `prtr`, `drtr`, `trtr` |
| `~/.profile.local` | `.profile` | `prtr`, `crtr`, `drtr`, `trtr` |

These hold host-specific env vars (`OLLAMA_HOST`), headless auth tokens, platform SDK paths, shell helpers, and tool completions. `~/.profile.local` holds `INFISICAL_TOKEN` on all nodes — unmanaged, do not delete.

### SSH Execution Patterns

```bash
# Bare cmd — sshd sources .bashrc → .profile; tools available
ssh drtr 'chezmoi update --force'

# Explicit login shell — .profile sources directly; tools available
ssh drtr 'bash -l -c "mise install --yes"'

# WRONG — do not use zsh for cluster ops
ssh drtr 'zsh -l -c "chezmoi doctor"'
```

### Per-Node Notes

| Node | Note |
|------|------|
| crtr | RPi5 arm64; 1-2s login latency is normal (mise activate on slow CPU) |
| drtr | `OLLAMA_HOST` not set in bash context; add to `~/.profile.local` if needed |
| prtr | `OLLAMA_HOST` in `.zprofile`/`.zshrc.local` only — inert under bash; add to `~/.profile.local` if needed |
| all | `~/.profile.local` holds `INFISICAL_TOKEN` — unmanaged, do not delete |
