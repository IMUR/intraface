# STATE — sorter live snapshot

**Snapshot baseline:** 2026-09-23 (post GPU driver alignment; enrolment day was 2026-09-20)
**Authority:** Point-in-time observation. Verify against live state before
trusting any row older than ~7 days. `ssh srtr '...'` for live checks.

## Hardware

| Field | Value |
|-------|-------|
| Board | Supermicro X10DAi rev 1.102 — BIOS 3.4 (2021-10-04), boot path legacy (UEFI switch deferred) |
| CPU | 2× Xeon E5-2687W v4 (24C/48T total) |
| OS | Debian 13 trixie, headless |
| RAM | 12× 16 GiB RDIMM DDR4-2133 ECC chipkill — 192 GiB installed, ≈188.8 GiB kernel-visible; 6 DIMMs/socket, NUMA balanced; EDAC mc0–mc3 CE/UE = 0 |
| GPU | 3× NVIDIA: **GTX 1080 8 GiB @ Slot 1** (`02:00.0`, NUMA 0) · **GTX 1080 8 GiB @ Slot 3** (`03:00.0`, NUMA 0) · **GTX 970 4 GiB @ Slot 5** (`81:00.0`, NUMA 1) — driver **nvidia 550.163.01** (dkms, node-specific apt layer), CUDA 12.4 userspace, persistence on, 20 GiB VRAM total. Console framebuffer armed (nvidia-drm `modeset=1 fbdev=1`) — verifies at next boot. Story: PROVISIONING §9–§10 |
| Storage | 1 internal drive: Crucial MX500 500 GB = `sda` — ESP 512M · bios-grub 1M · swap 8G · root 457.3G ext4 |
| RTC | CR2032 suspect — clock dies on full power loss; NTP re-sync required after every cold boot |

## Role

**Deep-time machine:** durable memory/context, database services, backend
inference for smaller/non-LLM models. Managed-but-not-HA (DECISIONS 0003).

## Network

| Interface | Address | State |
|-----------|---------|-------|
| `enp5s0` | `192.168.254.44/24` | UP, primary (operator-configured static) |
| `tailscale0` | `100.64.0.6/32` | UP — tailnet name `s`, MagicDNS `s.rtr.rtr.dev` |

History: bootstrapped while daisy-chained through prtr
(`192.168.100.137/24`, routed via `192.168.100.1`); moved to direct gateway
connection 2026-09-20 — L2 adjacency verified (direct routes + ARP
REACHABLE to crtr/prtr/drtr), multicast VRRP viable.

Second onboard NIC `enp6s0` DOWN, configless. PCIe population has shuffled
predictable NIC names before (bus renumbering); hardening queued: match
`10-wired.network` by MAC, not `Name=`.

## Cluster membership

| Layer | State |
|---|---|
| ops (chezmoi/mise) | ✅ enrolled 2026-09-20 — source `~/.inf/ops`, 33 tools, `mise doctor` clean, skills via `~/.inf/skills` symlinks |
| keepalived | ✅ VI_1 BACKUP priority 40 — verified BACKUP, no vIP claim, 0 MASTER transitions |
| GlusterFS | ❌ nothing — brick/mount decision open |
| HA services (the nine) | ❌ unit files deployed (inert); binaries + UID:GID parity not provisioned |

## DNS

`/etc/hosts` carries vIP entries for `git/sch/vpn/dtb/box/ktr.rtr.dev`
(DECISIONS 0004). LAN DNS resolves service names to the WAN IP otherwise.

## Open items

1. **GlusterFS decision** — client mount (needs a variant `mnt-gfs.mount`
   pointing at a member brick — the fabric unit mounts `localhost:/gfs`) vs
   arbiter brick (peer probe = cluster-level change) vs nothing. Tier 0+
   only; never a full brick (DECISIONS 0003).
2. **Workload service layer** — define the actual deep-time services
   (databases, memory stores, inference backends), their ports/uids (operator
   sign-off required per crtr-config conventions), and systemd unit homes.
   Node-specific service units are out of int/ops scope until the operator
   rules on a `workloads/<node>/` convention.
3. **Backup story for durable state** — highest durability priority in the
   cluster; restic pattern (gfs-backup precedent) aimed at sorter's stores.
   Nothing exists yet.
4. **Service exposure path** — tailnet (`s.rtr.rtr.dev`) recommended as
   prtr-independent primary; LAN direct once `.44` DNS/hosts entries spread.
5. **Inventory touchpoints pending cluster-side** — ops `AGENTS.md` node
   table, `remotes.md`, rewritten rtr-ops skill node list, canon (blocked:
   canon untrusted).
6. **Toolchain drift watch** — mise 2026.9.12 here vs 2026.9.11 on the three
   original nodes (self-update raced the cluster); align at next
   cluster-wide `mise self-update`.
7. **Inference readiness** — driver layer DONE 2026-09-23: nvidia 550.163.01
   (Maxwell+Pascal branch; exact parity with drtr/prtr's 615 is
   hardware-impossible — that generation dropped Maxwell/Pascal). Remaining:
   CUDA userspace deferred until a workload names its runtime (12.4-era;
   prtr's 13.1 toolkit cannot target CC 5.2/6.1). DECISIONS entry if the
   operator wants the cross-node driver policy recorded.
8. **NIC MAC-bind hardening** — switch `10-wired.network` match from
   `Name=enp5s0` to MAC, closing the name-shuffle failure mode.
9. **CR2032 replacement** — at next power-down window; BIOS clock check
   confirms urgency.
# STATE — sorter live snapshot

**Snapshot baseline:** 2026-09-23 (post GPU driver alignment; enrolment day was 2026-09-20)
**Authority:** Point-in-time observation. Verify against live state before
trusting any row older than ~7 days. `ssh srtr '...'` for live checks.

## Hardware

| Field | Value |
|-------|-------|
| Board | Supermicro X10DAi rev 1.102 — BIOS 3.4 (2021-10-04), boot path legacy (UEFI switch deferred) |
| CPU | 2× Xeon E5-2687W v4 (24C/48T total) |
| OS | Debian 13 trixie, headless |
| RAM | 12× 16 GiB RDIMM DDR4-2133 ECC chipkill — 192 GiB installed, ≈188.8 GiB kernel-visible; 6 DIMMs/socket, NUMA balanced; EDAC mc0–mc3 CE/UE = 0 |
| GPU | 3× NVIDIA: **GTX 1080 8 GiB @ Slot 1** (`02:00.0`, NUMA 0) · **GTX 1080 8 GiB @ Slot 3** (`03:00.0`, NUMA 0) · **GTX 970 4 GiB @ Slot 5** (`81:00.0`, NUMA 1) — driver **nvidia 550.163.01** (dkms, node-specific apt layer), CUDA 12.4 userspace, persistence on, 20 GiB VRAM total. Console framebuffer armed (nvidia-drm `modeset=1 fbdev=1`) — verifies at next boot. Story: PROVISIONING §9–§10 |
| Storage | 1 internal drive: Crucial MX500 500 GB = `sda` — ESP 512M · bios-grub 1M · swap 8G · root 457.3G ext4 |
| RTC | CR2032 suspect — clock dies on full power loss; NTP re-sync required after every cold boot |

## Role

**Deep-time machine:** durable memory/context, database services, backend
inference for smaller/non-LLM models. Managed-but-not-HA (DECISIONS 0003).

## Network

| Interface | Address | State |
|-----------|---------|-------|
| `enp5s0` | `192.168.254.44/24` | UP, primary (operator-configured static) |
| `tailscale0` | `100.64.0.6/32` | UP — tailnet name `s`, MagicDNS `s.rtr.rtr.dev` |

History: bootstrapped while daisy-chained through prtr
(`192.168.100.137/24`, routed via `192.168.100.1`); moved to direct gateway
connection 2026-09-20 — L2 adjacency verified (direct routes + ARP
REACHABLE to crtr/prtr/drtr), multicast VRRP viable.

Second onboard NIC `enp6s0` DOWN, configless. PCIe population has shuffled
predictable NIC names before (bus renumbering); hardening queued: match
`10-wired.network` by MAC, not `Name=`.

## Cluster membership

| Layer | State |
|---|---|
| ops (chezmoi/mise) | ✅ enrolled 2026-09-20 — source `~/.inf/ops`, 33 tools, `mise doctor` clean, skills via `~/.inf/skills` symlinks |
| keepalived | ✅ VI_1 BACKUP priority 40 — verified BACKUP, no vIP claim, 0 MASTER transitions |
| GlusterFS | ❌ nothing — brick/mount decision open |
| HA services (the nine) | ❌ unit files deployed (inert); binaries + UID:GID parity not provisioned |

## DNS

`/etc/hosts` carries vIP entries for `git/sch/vpn/dtb/box/ktr.rtr.dev`
(DECISIONS 0004). LAN DNS resolves service names to the WAN IP otherwise.

## Open items

1. **GlusterFS decision** — client mount (needs a variant `mnt-gfs.mount`
   pointing at a member brick — the fabric unit mounts `localhost:/gfs`) vs
   arbiter brick (peer probe = cluster-level change) vs nothing. Tier 0+
   only; never a full brick (DECISIONS 0003).
2. **Workload service layer** — define the actual deep-time services
   (databases, memory stores, inference backends), their ports/uids (operator
   sign-off required per crtr-config conventions), and systemd unit homes.
   Node-specific service units are out of int/ops scope until the operator
   rules on a `workloads/<node>/` convention.
3. **Backup story for durable state** — highest durability priority in the
   cluster; restic pattern (gfs-backup precedent) aimed at sorter's stores.
   Nothing exists yet.
4. **Service exposure path** — tailnet (`s.rtr.rtr.dev`) recommended as
   prtr-independent primary; LAN direct once `.44` DNS/hosts entries spread.
5. **Inventory touchpoints pending cluster-side** — ops `AGENTS.md` node
   table, `remotes.md`, rewritten rtr-ops skill node list, canon (blocked:
   canon untrusted).
6. **Toolchain drift watch** — mise 2026.9.12 here vs 2026.9.11 on the three
   original nodes (self-update raced the cluster); align at next
   cluster-wide `mise self-update`.
7. **Inference readiness** — driver layer DONE 2026-09-23: nvidia 550.163.01
   (Maxwell+Pascal branch; exact parity with drtr/prtr's 615 is
   hardware-impossible — that generation dropped Maxwell/Pascal). Remaining:
   CUDA userspace deferred until a workload names its runtime (12.4-era;
   prtr's 13.1 toolkit cannot target CC 5.2/6.1). DECISIONS entry if the
   operator wants the cross-node driver policy recorded.
8. **NIC MAC-bind hardening** — switch `10-wired.network` match from
   `Name=enp5s0` to MAC, closing the name-shuffle failure mode.
9. **CR2032 replacement** — at next power-down window; BIOS clock check
   confirms urgency.
