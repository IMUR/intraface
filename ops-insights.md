# Ops Insights — Cluster Quirks, Friction & What Still Works

> Generated 2026-07-17. Records operational observations from cross-node skill sync and mise upgrade investigation.

---

## 1. SSH Hopping

### All directional pairs work (crtr ↔ drtr ↔ prtr)

SSH is configured via `~/.ssh/config` with host aliases. Every pair connects:

```
crtr -> drtr  ✅ (cooperator)
crtr -> prtr  ✅
drtr -> crtr  ✅
drtr -> prtr  ✅
prtr -> crtr  ✅
prtr -> drtr  ✅
```

**Caveat:** SSH uses `ControlMaster auto` with socket multiplexing (`~/.ssh/sockets/`). If the control master dies (node reboot, SSH config reload), stale sockets cause "Connection closed" errors. Fix: `ssh -O exit <host>` then retry.

### Passwordless sudo confirmed on all nodes

All three nodes accept passwordless `sudo` from the SSH user.

---

## 2. Skills Layout — Five Targets, One Source of Truth

### prtr is the deployment source

Skills live on prtr in **five identical targets**, each containing the same 55 skills:

| Target | Path |
|--------|------|
| `.agents/skills/` | `~/.agents/skills/` |
| `.claude/skills/` | `~/.claude/skills/` |
| `.gemini/antigravity/skills/` | `~/.gemini/antigravity/skills/` |
| `.config/opencode/skills/` | `~/.config/opencode/skills/` |
| `.cursor/skills/` | `~/.cursor/skills/` |

Plus a separate **Cursor SDK skills** directory (19 skills, 51 files):
| Target | Path |
|--------|------|
| `.cursor/skills-cursor/` | `~/.cursor/skills-cursor/` |

### How sync works

`rtr-teach` uses `scripts/skills-sync` which rsyncs from a monorepo (`/mnt/ops/prj/skills/.agent/skills/`) into all five targets. The monorepo lives on an autofs mount at `/mnt/ops/` which is **currently down on all nodes** (drive failure).

**Syncing from prtr to any node:**
```bash
ssh <target> "rsync -av --delete prtr:~/.agents/skills/ ~/.agents/skills/"
ssh <target> "rsync -av --delete prtr:~/.claude/skills/ ~/.claude/skills/"
ssh <target> "rsync -av --delete prtr:~/.gemini/antigravity/skills/ ~/.gemini/antigravity/skills/"
ssh <target> "rsync -av --delete prtr:~/.config/opencode/skills/ ~/.config/opencode/skills/"
ssh <target> "rsync -av --delete prtr:~/.cursor/skills/ ~/.cursor/skills/"
ssh <target> "rsync -av --delete prtr:~/.cursor/skills-cursor/ ~/.cursor/skills-cursor/"
```

**Parent directories may not exist** (`.agents/`, `.gemini/`, `.config/opencode/`). Create them first:
```bash
ssh <target> "mkdir -p ~/.agents ~/.gemini/antigravity ~/.config/opencode"
```

### crtr was fully empty

crtr had **zero** skill targets before sync. It still has `.claude/remote/` (Claude Code CLI runtime) and `.cursor/skills-cursor/` (19 Cursor SDK skills), but none of the 5 managed skill directories existed.

### drtr and prtr match

drtr and prtr have all 5 targets with identical content (verified via file-list diff).

---

## 3. Mise — The Biggest Footgun Source

### mise is available everywhere, but caching is per-node

`mise` lives at `~/.local/bin/mise` on all nodes, added to PATH via `~/.profile` (which SSH login shells source automatically). All `mise` subcommands work in plain `ssh node 'mise ...'`.

**The cache is per-node and version-specific.** `mise latest <tool>` reads from:
- `~/.cache/mise/<tool>/remote_versions-<hash>.msgpack.z`
- `~/.cache/mise/github/https-api-github-com-<repo>-latest-hosted-<hash>.msgpack.z`

The hash differs between mise versions (e.g., 2026.7.5 vs 2026.5.16), so each node has independent cache state. **A stale cache means `mise latest` returns an older version than what GitHub actually has.**

### mise version matters

| Node | mise version | Architecture |
|------|-------------|-------------|
| crtr | 2026.7.5 | linux-arm64 |
| drtr | 2026.5.16 | linux-x64 |
| prtr | 2026.5.16 | linux-x64 |

crtr's newer mise (2026.7.5) cached older values than drtr/prtr (2026.5.16), even though the GitHub releases are identical.

### `mise upgrade` vs `mise upgrade --bump`

| Flag | Behavior |
|------|----------|
| `mise upgrade` | Installs latest for `latest` tools; keeps pinned versions as-is. Does NOT write to config. |
| `mise upgrade --bump` | Installs latest for **all** tools including pinned ones, and writes the resolved version to config. |

`--bump` on `node = "24.16.0"` would resolve to `26.5.0` (two major versions). Use without `--bump` to keep pins.

### `mise upgrade` is non-destructive

Tools are uninstalled then reinstalled sequentially. If interrupted mid-cycle, some tools may be on old versions while others are new. No data loss — just a partial state until next run.

### `mise upgrade --dry-run` is safe and useful

`mise upgrade -n` previews what will happen without touching anything. Use this before every cluster-wide upgrade.

### minimum_release_age blocks recent releases

mise defaults to a 24-hour minimum release age. Tools released within 24h (e.g., `rust 1.97.1`) show as "newer" in `outdated` but `upgrade` ignores them until the window passes.

### Fixing stale cache

```bash
ssh <node> "rm -rf ~/.cache/mise/<tool>/"
ssh <node> "rm ~/.cache/mise/github/https-api-github-com-<repo>-latest-hosted-*.msgpack.z"
ssh <node> "mise upgrade --yes"
```

Or force specific versions:
```bash
ssh <node> "mise use --global pi@0.80.10 && mise install pi"
```

### `mise self-update` needed separately

mise itself is managed by mise (ironically), but `mise upgrade` doesn't update the mise binary. Run `mise self-update --yes` separately.

---

## 4. Dotfiles — chezmoi

### chezmoi status is reliable

`chezmoi status` (empty output = clean) works on all nodes via `ssh node 'cd ~/.local/share/chezmoi && chezmoi status'`.

### Dotfiles are at the same commit on all nodes

All three nodes were at `adf836c fix(profile): stop exporting _PROFILE_LOADED, fix stale doc path refs`.

### Autofs mount `/mnt/ops/` is down

The monorepo at `/mnt/ops/prj/skills` is inaccessible on all nodes. The `rtr-ops` script expects it for parsing tools from config. Direct access via `~/.local/share/chezmoi/dot_config/mise/config.toml` works as a fallback.

### `chezmoi update --force` has no dry-run

It always overwrites. Safe only if confident no node has drifted.

---

## 5. Per-Node Overrides (unmanaged)

These are node-specific files not tracked by chezmoi. They differ between nodes:

| File | crtr | drtr | prtr |
|------|------|------|------|
| `~/.profile.local` | absent | ✅ infisical token auth | ✅ infisical token auth |
| `~/.zshrc.local` | absent | ✅ `PROTON_PASS_KEY_PROVIDER=fs` | ✅ `PROTON_PASS_KEY_PROVIDER=fs` + `OLLAMA_HOST` + openclaw completion |
| `~/.zprofile` | absent | absent | ✅ `OLLAMA_HOST=http://127.0.0.1:7711` |

**Important:** `.zprofile` and `.zshrc.local` are zsh-specific. In bash login shells (`ssh node 'bash -l -c ...'`), only `.profile` is sourced. `OLLAMA_HOST` on prtr is set in both `.zshrc.local` and `.zprofile` — in bash, the `.zprofile` version is what matters.

---

## 6. PATH Resolution

### All critical binaries resolve through mise

`node`, `python3`, `python`, `go`, `bun`, `chezmoi`, `infisical`, `pi` — all resolve via mise install paths on every node.

### `cargo` resolves outside mise

`cargo` → `~/.cargo/bin/cargo` on all nodes. This is mise's standard Rust toolchain integration (mise creates a symlink). Not a problem, just worth noting.

### `~/.local/bin` is always on PATH

`~/.profile` adds `~/.local/bin` to PATH. mise's own binary lives there. This is intentional and correct.

---

## 7. What Still Works (Verified)

- ✅ SSH between all node pairs
- ✅ Passwordless sudo on all nodes
- ✅ mise commands in plain SSH sessions (no login shell needed)
- ✅ `mise upgrade --yes` — installs latest for `latest` tools, keeps pins
- ✅ `mise upgrade --dry-run` — safe preview
- ✅ `rsync -av --delete` from prtr to any node for skill sync
- ✅ chezmoi status check on all nodes
- ✅ All 5 skill targets identical on prtr, drtr, prtr
- ✅ crtr fully synced to match prtr (55 skills × 5 targets + 19 cursor SDK skills)

## 8. What's Different / Fragmented

- ⚠️ mise versions differ across nodes (2026.7.5 vs 2026.5.16) — causes cache divergence
- ⚠️ `/mnt/ops/prj/skills` autofs mount is down — can't use `rtr-ops` scripts
- ⚠️ crtr's config now has explicit versions (`pi = "0.80.10"`) while drtr/prtr say `latest` — functionally identical but config-parity broken
- ⚠️ `.cursor/skills-cursor/` has manifest file differences (`.cursor-managed-skills-manifest.json`, `.sync-manifest.json`) and auto-generated `canvas/sdk/*.d.ts` files drift between nodes

---

## 9. Upgrade Playbook (Safe)

```bash
# 1. Preview on all nodes
for n in crtr drtr prtr; do
  echo "=== $n ==="
  ssh $n "mise upgrade -n 2>&1"
done

# 2. Canary first
ssh crtr "mise upgrade --yes 2>&1"

# 3. Then others
ssh drtr "mise upgrade --yes 2>&1"
ssh prtr "mise upgrade --yes 2>&1"

# 4. Verify
for n in crtr drtr prtr; do
  echo "--- $n ---"
  ssh $n "mise ls --current 2>&1 | grep -E 'pi|node|python|rust|infisical'"
done
```

### Fixing stale cache on a node

```bash
ssh <node> "rm -rf ~/.cache/mise/<tool>/"
ssh <node> "rm ~/.cache/mise/github/https-api-github-com-<repo>-latest-hosted-*.msgpack.z"
ssh <node> "mise upgrade --yes 2>&1"
```

Or force version:
```bash
ssh <node> "mise use --global <tool>@<version> && mise install <tool>"
```

---

## 10. SSH Config Notes

The SSH config at `~/.ssh/config` uses:
- `ControlMaster auto` with `ControlPath ~/.ssh/sockets/%r@%h:%p`
- `ServerAliveInterval 60` / `ServerAliveCountMax 3`
- `IdentityFile` differs for prtr (`id_ed25519_self`) vs crtr/drtr (`id_ed25519`)

All nodes have both `id_ed25519` and `id_ed25519_self` keys, so any node can SSH to any other using either key.

---

*End of document. Keep this updated as new quirks are discovered.*
