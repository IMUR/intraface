# Intraface Restructure — Execution Plan

**Status:** Ready for execution after tree-shape lock
**Prerequisite:** Tree-shape decision (Section 1) and charter cleanup (Section 2)
**Source-of-truth docs:** `intraface-charter.md`, `oversight-agent-prd.md`

---

## What this plan is — and isn't

**Is:** A structural reorganization that creates the Intraface project at `~/prj/intraface/` and `~/.intraface/`, lands the charter, establishes runtime registries with cited values, and migrates the verified-working subprocess pattern into the new home.

**Isn't:** A fix for the existing `summarize.ts` code's charter violations. The current code (path-parameter source-as-string, grammar without provenance) fails Tests 1 and 2. **It is not being ported.** The subprocess *pattern* (spawn with argv array, no shell, timeout, JSON-extract-on-close) is being preserved because it's verified working and charter-neutral; the summarize *function* is not.

The first real Unit under this structure will be built against the charter from the start — schema-with-provenance, path-based invocation, domain primer. That work happens *after* this plan executes, not during.

---

## Section 1 — Tree shape (REQUIRES DECISION)

The layout must be locked before Phase 1. With one Unit today both options work; renaming is free before the initial commit and annoying after.

### Option A — File-type grouping

```
~/prj/intraface/
├── lib/
│   └── spawn-llama.ts          # shared subprocess helper
├── grammars/
│   └── *.gbnf                  # one per Unit that uses grammar constraint
├── prompts/
│   └── *.ts                    # one per Unit
├── types/
│   └── *.ts                    # shared interfaces
├── extension.ts                # Pi extension entry
└── docs/
```

**When it wins:** Units share infrastructure and differ only in (prompt, grammar) tuples.

### Option B — One-folder-per-Unit (recommended)

```
~/prj/intraface/
├── lib/
│   └── spawn-llama.ts          # shared subprocess helper
├── units/
│   └── summarize/              # or "extract" once that shape exists
│       ├── prompt.ts
│       ├── grammar.gbnf
│       ├── schema.ts
│       └── handler.ts
├── extension.ts                # Pi extension entry — imports from units/
└── docs/
```

**When it wins:** Units have substantively different logic, or when custody visibility matters most (a Unit is a folder, not a scatter).

**My lean:** Option B. The charter's Test 5 makes Units first-class custodial things. First-class things get folders. Cost at N=1 is small; cost of restructuring at N=2 is real. This is the layout the rest of the plan assumes; swap to A by adjusting paths only.

---

## Section 2 — Charter cleanup (REQUIRED BEFORE MOVE)

The on-disk `intraface-charter.md` has two stale references that need fixing before it lands in `~/prj/intraface/docs/`:

**Fix 1 — frontmatter line 4:**

Current:
```yaml
status: locked concept — unlocked items are marked and collected near the end
```

Replace with:
```yaml
status: locked concept
```

Rationale: the Unlocked section was removed when autonomy/leverage was resolved via "Intraface does not choose its own leash" (fourth bullet under "What Intraface is not"). The frontmatter wasn't updated.

**Fix 2 — line 27 parenthetical:**

Current:
```
(A deeper cognitive-science framing may exist for the Executor/Protext pair taken together, rather than for either alone — left open; see Unlocked.)
```

Replace with:
```
(A deeper cognitive-science framing for the Executor/Protext pair taken together, rather than for either alone, may exist; that is a question for a future document, not this charter.)
```

Rationale: defers the question without pointing at a section that doesn't exist.

---

## Section 3 — Payload: what ports, what doesn't

| Source file | Action | Destination | Why |
|---|---|---|---|
| `summarize.ts` (spawn helper + summarize function) | **Port the spawn helper only** — extract lines 27-92 (the spawn/timeout/JSON-extract pattern), strip the summarize-specific prompt and the `summarize()` function wrapper | `~/prj/intraface/lib/spawn-llama.ts` | The pattern is verified working; the function around it fails Tests 1 and 2 |
| `summary.gbnf` | **Port unchanged for now** | `~/prj/intraface/units/summarize/grammar.gbnf` (or `grammars/` under Option A) | Will be retired when the first extraction-shape Unit ships, but currently the working constraint mechanism |
| `test-spawn*.ts` (4 files) | **Do not port** | — | All contain the spawn-sh-c bug pattern. Debris from the debugging session |
| `test-model.ts` | **Do not port** | — | Phase 1 node-llama-cpp test, abandoned |
| `package.json` | **Port, renamed** | `~/prj/intraface/package.json` with `name: "intraface"` | Project metadata, no deps yet |
| `.gitignore` | **Port, expanded** | `~/prj/intraface/.gitignore` | See Section 9 |
| Deployed `~/.pi/agent/extensions/summarize.ts` | **Replace with thin shim** | `~/.pi/agent/extensions/intraface.ts` (real file, not symlink) | See Section 8 |

### Why `-j` (runtime schema) is not the constraint mechanism

Verified 2026-07-06 on mainline build `9861 (c8ae9a750)`:

```
$ llama-cli ... -j '{"type":"object","properties":{...}}' ...
0.00.963.493 E common_sampler_init: error initializing grammar sampler for grammar:
  ... [grammar shown correctly] ...
0.00.963.528 E srv send_error: task id = 0, error: Failed to initialize samplers: std::exception
```

The schema-to-grammar conversion works; sampler init throws. The `-j` flag is broken on this build. Precompiled `.gbnf` via `--grammar-file` is the only working constraint mechanism. The `grammars/` directory (or `units/<name>/grammar.gbnf` under Option B) must exist until mainline fixes the sampler bug. Revisit when build updates.

---

## Phase 1 — Establish structure (no code moves yet)

Create the empty homes. Nothing breaks because nothing points at them yet.

```bash
mkdir -p ~/prj/intraface/lib
mkdir -p ~/prj/intraface/docs
mkdir -p ~/prj/intraface/units/summarize    # Option B layout
mkdir -p ~/.intraface/models/lfm2.5-1.2b-instruct
mkdir -p ~/.intraface/state
```

**Verify:**

```bash
ls ~/prj/intraface/   # lib, docs, units (Option B)
ls ~/.intraface/      # models, state
```

**Gate:** Don't proceed until both directories exist with the right layout.

---

## Phase 2 — Move model files (DESTRUCTIVE)

This phase deletes three rejected model files. Locked decision per user approval 2026-07-06.

```bash
# Move the surviving model
mv ~/prj/subagent-summarize/models/LFM2.5-1.2B-Instruct-Q4_K_M.gguf \
   ~/.intraface/models/lfm2.5-1.2b-instruct/

# Delete rejected models (locked decision)
rm ~/prj/subagent-summarize/models/LFM2-2.6B-Transcript-Q4_K_M.gguf
rm ~/prj/subagent-summarize/models/LFM2-2.6B-Transcript-Q5_K_M.gguf
rm ~/prj/subagent-summarize/models/LFM2.5-8B-A1B-Q5_K_M.gguf

# Old models directory is now empty; remove it
rmdir ~/prj/subagent-summarize/models
```

**Verify (cited values):**

```bash
stat -c '%n %s' ~/.intraface/models/lfm2.5-1.2b-instruct/*.gguf
# Expected: 730895168 bytes (verified 2026-07-06)

ls ~/prj/subagent-summarize/models 2>&1
# Expected: error, directory gone
```

**Gate:** Don't proceed until the surviving model is verified at the new path with the expected size.

---

## Phase 3 — Land the charter (with cleanup)

Apply Section 2 fixes first, then move.

```bash
# Move the charter
mv ~/prj/prtr-config/intraface-charter.md ~/prj/intraface/docs/charter.md
```

**Verify:**

```bash
head -10 ~/prj/intraface/docs/charter.md
# Should show "status: locked concept" with no "unlocked items" text
grep "see Unlocked" ~/prj/intraface/docs/charter.md
# Should return nothing (deferral rewritten)
```

**Gate:** Charter is at new home, cleanup applied, no stale references.

---

## Phase 4 — Port the spawn helper (charter-neutral pattern only)

Create `~/prj/intraface/lib/spawn-llama.ts` containing the verified subprocess pattern, stripped of the summarize-specific code. Target shape:

```typescript
import { spawn } from "child_process";

export interface SpawnResult {
  stdout: string;
  stderr: string;
  exitCode: number | null;
  timedOut: boolean;
}

export interface SpawnOptions {
  timeoutMs?: number;       // default 60000
  env?: Record<string, string>;
}

/**
 * Spawn llama-cli with argv array — no shell wrapper, no string interpolation.
 * The pattern verified working 2026-07-03 (9.8s wall, exit 0, valid JSON
 * on AGENTS.md source). See docs/charter.md Test 3 (router) and the
 * "Don't reintroduce the spawn-sh-c bug" warning.
 */
export function spawnLlama(args: string[], opts: SpawnOptions = {}): Promise<SpawnResult> {
  const timeoutMs = opts.timeoutMs ?? 60000;
  const env = { ...process.env, CUDA_VISIBLE_DEVICES: "", ...opts.env };

  return new Promise((resolve, reject) => {
    const child = spawn("llama-cli", args, {
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);

    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ stdout, stderr, exitCode: code, timedOut });
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/**
 * Extract the first JSON object {...} from stdout. Used by Unit handlers
 * to peel the model output off any spinner noise.
 */
export function extractJson(stdout: string): unknown | null {
  const match = stdout.trim().match(/\{[\s\S]*\}/);
  if (!match) return null;
  try {
    return JSON.parse(match[0]);
  } catch {
    return null;
  }
}
```

**Verify (compiles, imports resolve):**

```bash
cd ~/prj/intraface && node --experimental-strip-types -e '
  import("./lib/spawn-llama.ts").then(m => {
    console.log("exports:", Object.keys(m));
    console.log("spawnLlama type:", typeof m.spawnLlama);
    console.log("extractJson type:", typeof m.extractJson);
  });
'
```

**Expected:** exports list both functions; both are "function". No execution of llama-cli at this stage — just module loading.

**Gate:** Module loads cleanly. Don't proceed until imports resolve.

---

## Phase 5 — Port the grammar (interim, will be replaced)

The current `summary.gbnf` enforces structure but no provenance. It's being ported *temporarily* because (a) `-j` is broken on this build so we need a grammar file, and (b) the first real Unit work will replace it with a schema-with-provenance grammar.

```bash
cp ~/prj/subagent-summarize/summary.gbnf ~/prj/intraface/units/summarize/grammar.gbnf
```

**Verify:**

```bash
diff ~/prj/subagent-summarize/summary.gbnf ~/prj/intraface/units/summarize/grammar.gbnf
# Expected: identical
```

**Mark as interim:** Add a header comment to the ported grammar:

```bash
cat > ~/prj/intraface/units/summarize/grammar.gbnf <<'EOF'
# INTERIM — fails charter Test 2 (proof). Enforces structure but not
# provenance (no quote/span/source fields). Replaced when the first
# extraction-shape Unit ships. Ported 2026-07-06 from subagent-summarize.

root ::= "{" ws "\"summary\"" ws ":" ws string "," ws "\"key_points\"" ws ":" ws array "," ws "\"decisions\"" ws ":" ws array "," ws "\"action_items\"" ws ":" ws array "," ws "\"open_questions\"" ws ":" ws array ws "}" ws

array  ::= "[" ws (string ("," ws string)*)? "]" ws
string ::= "\"" ([^"\\\x7F\x00-\x1F] | "\\" (["\\bfnrt] | "u" [0-9a-fA-F]{4}))* "\"" ws
ws     ::= | " " | "\n" [ \t]{0,20}
EOF
```

**Gate:** Grammar at new home with interim header.

---

## Phase 6 — Land runtime registries (cited values only)

Every value comes from a cited command run on 2026-07-06. No approximations, no memory.

### `~/.intraface/models.toml`

```toml
# Intraface model registry
# Every value observed 2026-07-06. No approximations.

["lfm2.5-1.2b-instruct-q4-k-m"]
path = "/home/prtr/.intraface/models/lfm2.5-1.2b-instruct/LFM2.5-1.2B-Instruct-Q4_K_M.gguf"
size_bytes = 730895168           # from: stat -c %s
quant = "Q4_K_M"
source = "https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF"
verified = "2026-07-06"
role = "unit"

["glm-4.7-flash-q8"]
path = "/home/prtr/models/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf"
size_bytes = 31842799488         # from: stat -c %s
quant = "Q8_0"
source = "https://huggingface.co/zai-org/GLM-4.7-Flash"
verified = "2026-07-06"
role = "core"
custody = "external"             # not under ~/.intraface/ — see charter Test 5 note
```

### `~/.intraface/engines.toml`

```toml
# Intraface engine registry
# Versions from --version, paths verified 2026-07-06.

["mainline-llama-cpp"]
path = "/home/prtr/prj/llama.cpp/build/bin"
version = "9861 (c8ae9a750)"     # from: llama-cli --version
built_with = "GNU 14.2.0"
verified = "2026-07-06"
supports_lfm2 = true
deployed_via_local_bin_symlinks = true   # ~/.local/bin/llama-* symlinks point here
notes = "Mainline build. Used by Unit invocations. Note: -j/--json-schema is broken on this build (sampler init throws); use --grammar-file until mainline updates."

["ik-llama-cpp"]
path = "/home/prtr/prj/ik_llama.cpp/build/bin"
version = "4681 (86d8e9a1)"      # from: llama-server --version
built_with = "cc (Debian 14.2.0-19) 14.2.0"
verified = "2026-07-06"
supports_lfm2 = false             # does not support LFM2 architecture
supports_glm = true               # has -cram, --ctx-checkpoints, -mla flags
deployed_via_local_bin_symlinks = false
notes = "GLM service engine. Invoked by absolute path only — not on PATH intentionally."
```

### `~/.intraface/services.toml` (Intraface components only)

Per charter Test 5 (custody), this file **only** contains Core and Unit services. Node-level services (Ollama, XTDB, OpenFang) belong in prtr-config, referenced from here if needed.

```toml
# Intraface services registry
# Per charter Test 5: Intraface owns Core and Unit services only.
# Node services (Ollama, XTDB, OpenFang, Cockpit) live in prtr-config.

["glm-4.7-flash"]
port = 7712
engine_ref = "ik-llama-cpp"      # references engines.toml entry
model_ref = "glm-4.7-flash-q8"   # references models.toml entry
bind = "127.0.0.1"
launch_flags = [
  "-m", "/home/prtr/models/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf",
  "--host", "127.0.0.1",
  "--port", "7712",
  "-c", "98304",
  "-np", "1",
  "-ngl", "99",
  "--n-cpu-moe", "4",
  "-cram", "0",
  "--ctx-checkpoints", "0",
  "--jinja",
]
launch_flags_source = "/proc/634777/cmdline (decoded via tr '\\0' ' '), 2026-07-06"
systemd_unit = false
systemd_gap_note = "Launched manually from ik_llama.cpp tree; PPid 1 because launching shell exited. Will not survive reboot."
verified = "2026-07-06"
```

**Verify:**

```bash
ls ~/.intraface/*.toml
# Expected: engines.toml, models.toml, services.toml

# Spot-check cited values
stat -c %s ~/.intraface/models/lfm2.5-1.2b-instruct/LFM2.5-1.2B-Instruct-Q4_K_M.gguf
# Expected: 730895168 (matches models.toml entry)

stat -c %s /home/prtr/models/glm-4.7-flash/zai-org_GLM-4.7-Flash-Q8_0.gguf
# Expected: 31842799488 (matches models.toml entry)

tr '\0' ' ' < /proc/634777/cmdline
# Expected: matches launch_flags_source in services.toml
```

**Gate:** All cited values reproduce.

---

## Phase 7 — Write the extension shim (real file, NOT symlink)

Per the reviewer's correct catch on Node module resolution: a symlinked extension at `~/.pi/agent/extensions/intraface.ts` would dereference to `~/prj/intraface/extension.ts`, and bare-specifier imports like `"typebox"` would walk up from `~/prj/intraface/` looking for `node_modules/` — which won't exist.

**Solution:** `~/.pi/agent/extensions/intraface.ts` is a real file. It imports the project via absolute path (matching the current working pattern). The project owns the source; the deployed extension owns the deployment.

### Source: `~/prj/intraface/extension.ts`

```typescript
import { Type } from "typebox";
import { summarize } from "./units/summarize/handler.ts";

export default function (pi: any) {
  pi.registerTool({
    name: "summarize",
    label: "Summarize",
    description: "Summarize source text into structured JSON. NOTE: charter-violating shape — source text transits Core context. Interim; replaced when extraction-shape Unit ships.",
    promptSnippet: "Summarize source text into structured JSON output",
    parameters: Type.Object({
      source: Type.String({ description: "Source text to summarize" }),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const result = await summarize(params.source);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: {},
      };
    },
  });
}
```

This is the *interim* shape that maintains working behavior. It explicitly flags itself as charter-violating in its own description. When the extraction-shape Unit ships, this file changes — the tool description, parameters, and handler all get replaced.

### Source: `~/prj/intraface/units/summarize/handler.ts`

```typescript
import { spawnLlama, extractJson } from "../../lib/spawn-llama.ts";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MODEL_PATH = "/home/prtr/.intraface/models/lfm2.5-1.2b-instruct/LFM2.5-1.2B-Instruct-Q4_K_M.gguf";
const GRAMMAR_PATH = path.join(__dirname, "grammar.gbnf");

interface Summary {
  summary: string;
  key_points: string[];
  decisions: string[];
  action_items: string[];
  open_questions: string[];
}

export async function summarize(source: string): Promise<Summary> {
  // INTERIM: source as parameter fails charter Test 1 (attention).
  // Replaced when path-based invocation ships.
  const prompt = `Summarize this source:

"""
${source}
"""

Return JSON matching the schema: {summary, key_points[], decisions[], action_items[], open_questions[]}. Be specific; quote the source where useful. Use empty arrays for fields that don't apply.`;

  const args = [
    "-m", MODEL_PATH,
    "-n", "4000",
    "-ngl", "0",
    "-st",
    "--log-disable",
    "--no-display-prompt",
    "--grammar-file", GRAMMAR_PATH,
    "-p", prompt,
  ];

  const result = await spawnLlama(args);
  if (result.exitCode !== 0) {
    throw new Error(`llama-cli exited ${result.exitCode}\nSTDERR: ${result.stderr}`);
  }
  if (result.timedOut) {
    throw new Error(`llama-cli timed out\nSTDERR: ${result.stderr}`);
  }

  const json = extractJson(result.stdout);
  if (!json) {
    throw new Error(`No JSON found in output:\n${result.stdout}`);
  }
  return json as Summary;
}
```

### Deployment: `~/.pi/agent/extensions/intraface.ts` (REAL FILE, not symlink)

```typescript
// Intraface extension — deployed shim
// Source: ~/prj/intraface/extension.ts
// This file is a real copy (not symlink) so bare-specifier imports
// resolve from ~/.pi/'s node_modules, not the project's.
// Regenerate via: cp ~/prj/intraface/extension.ts ~/.pi/agent/extensions/intraface.ts

import { Type } from "typebox";
import { summarize } from "/home/prtr/prj/intraface/units/summarize/handler.ts";

export default function (pi: any) {
  pi.registerTool({
    name: "summarize",
    label: "Summarize",
    description: "Summarize source text into structured JSON. NOTE: charter-violating shape — source text transits Core context. Interim; replaced when extraction-shape Unit ships.",
    promptSnippet: "Summarize source text into structured JSON output",
    parameters: Type.Object({
      source: Type.String({ description: "Source text to summarize" }),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const result = await summarize(params.source);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: {},
      };
    },
  });
}
```

**Verify the deploy:**

```bash
# Remove old deployed extension
rm ~/.pi/agent/extensions/summarize.ts

# Write the new shim
cp ~/prj/intraface/extension.ts ~/.pi/agent/extensions/intraface.ts
# (then edit the import path in the deployed copy to be absolute — see below)

# Or write directly with the absolute import path already in place
```

**Important:** the deployed copy at `~/.pi/agent/extensions/intraface.ts` has `import { summarize } from "/home/prtr/prj/intraface/units/summarize/handler.ts"` (absolute path), while the source at `~/prj/intraface/extension.ts` has `import { summarize } from "./units/summarize/handler.ts"` (relative). This asymmetry is the cost of avoiding symlink-based deployment.

**End-to-end test:**

```bash
cd /tmp && timeout 60 pi --extension ~/.pi/agent/extensions/intraface.ts \
  --tools summarize \
  -p "Use the summarize tool on /home/prtr/prj/prtr-config/AGENTS.md" 2>&1 | tail -20
```

**Expected:** 9-10s wall, exit 0, valid 5-field JSON.

**Note on what this test does NOT prove:** per the reviewer's correct catch, this test uses the explicit "Use the summarize tool" crutch. It proves plumbing (registration, invocation, output parsing). It does **not** prove the Core auto-invokes the tool under normal operation. That is the Frame C problem; it remains open.

**Rollback if test fails:**

```bash
rm ~/.pi/agent/extensions/intraface.ts
# Restore the previous working deployment from the subagent-summarize repo
cp ~/prj/subagent-summarize/summarize.ts ~/.pi/agent/extensions/summarize.ts
# (and edit the import path back to the original)
```

**Gate:** End-to-end test passes. Tool produces valid JSON.

---

## Phase 8 — Write DEPLOYMENT.md

Create `~/prj/intraface/docs/DEPLOYMENT.md`:

```markdown
# Intraface — Deployment

This project is canonical source. Deployed artifacts reference it.

## Deployed extension (real file, not symlink)

`~/.pi/agent/extensions/intraface.ts` is a real copy of `~/prj/intraface/extension.ts`
with one modification: the import path to the handler is absolute
(`/home/prtr/prj/intraface/...`) instead of relative.

**Why not symlink:** Node's resolver dereferences symlinks and walks
`node_modules` from the real path. A symlink would look for `typebox`
in `~/prj/intraface/node_modules/`, which is gitignored and absent.
The real-file shim resolves `typebox` from `~/.pi/`'s dependencies.

**Regenerate after editing the source:**

```bash
cp ~/prj/intraface/extension.ts ~/.pi/agent/extensions/intraface.ts
# Then edit the handler import to absolute path:
# from:  from "./units/summarize/handler.ts"
# to:    from "/home/prtr/prj/intraface/units/summarize/handler.ts"
```

## Runtime registry (~/.intraface/)

Not symlinks — TOML registry entries pointing at observed paths.

- `models.toml` — one entry per model the system can invoke
- `engines.toml` — one entry per inference engine
- `services.toml` — Intraface-owned services only (Core + Units); node services live in prtr-config
- `state/` — runtime state, regenerable, never versioned

## Deletion probes (charter Test 5)

Deleting `~/prj/intraface/` breaks:
- The handler import in `~/.pi/agent/extensions/intraface.ts` (path dangles)
- Nothing else — the deployed extension is a real file with cached content

Deleting `~/.intraface/` breaks:
- Model and engine discovery (registry gone)
- Nothing in `~/prj/intraface/` source (paths are referenced, not imported)

Deleting `~/.pi/agent/extensions/intraface.ts` breaks:
- Pi doesn't load the Unit. Source at `~/prj/intraface/` is intact.

Deleting prtr-config breaks:
- Node-level facts. Intraface source at `~/prj/intraface/` is intact.

## Verification recipes

See `oversight-agent-prd.md` (in prtr-config) for sandbox-safe read patterns.
Key recipe for this project: `/proc/<pid>/cmdline` is binary; decode via
`tr '\0' ' ' < /proc/<pid>/cmdline`.
```

---

## Phase 9 — Write `.gitignore` and `package.json`

### `~/prj/intraface/.gitignore`

```
# Dependencies
node_modules/

# Model files (defensive — models live in ~/.intraface/models/, not here)
*.gguf
models/

# Build artifacts
*.tsbuildinfo
dist/

# Logs
*.log

# Runtime state (lives in ~/.intraface/state/, never here)
state/
```

### `~/prj/intraface/package.json`

```json
{
  "name": "intraface",
  "version": "0.1.0",
  "description": "Local-specialist harness for prtr. See docs/charter.md.",
  "type": "module",
  "scripts": {
    "test": "echo 'No tests yet' && exit 1"
  }
}
```

---

## Phase 10 — Cleanup

After all gates pass:

```bash
# Verify nothing in the new layout references the old directory
rg "subagent-summarize" ~/prj/intraface/ ~/.intraface/ ~/.pi/agent/extensions/ 2>&1
# Expected: no hits

# Remove the old working directory (its code has been ported or rejected)
rm -rf ~/prj/subagent-summarize

# Verify the new deployment still works without the old dir
cd /tmp && timeout 60 pi --extension ~/.pi/agent/extensions/intraface.ts \
  --tools summarize \
  -p "Use the summarize tool on /home/prtr/prj/prtr-config/AGENTS.md" 2>&1 | tail -10
```

**Final verification:**

```bash
ls ~/prj/subagent-summarize 2>&1
# Expected: directory gone

ls ~/prj/intraface/
# Expected: docs, lib, units, extension.ts, package.json, .gitignore

ls ~/.pi/agent/extensions/
# Expected: herdr-agent-state.ts, intraface.ts (no summarize.ts)

ls ~/.intraface/
# Expected: models, state, *.toml files

readlink -f ~/.pi/agent/extensions/intraface.ts
# Expected: /home/prtr/.pi/agent/extensions/intraface.ts (real file, not symlink)
```

---

## Phase 11 — Git init the new repo

Only after Phase 10 verification passes.

```bash
cd ~/prj/intraface
git init
git add .
git status   # verify what's staged
git commit -m "Initial: Intraface structure with summarize Unit (interim shape)"
```

**Do not push yet.** Create `rtr/intraface` on Forgejo via the UI first, then:

```bash
git remote add origin ssh://git@git.ism.la:6666/rtr/intraface.git
git push -u origin main
```

### On `rtr/subagent-summarize` (existing repo)

After `rtr/intraface` exists and is pushed, delete `rtr/subagent-summarize` via the Forgejo UI. Its working code is now in `rtr/intraface` (with the spawn helper preserved and the broken summarize function replaced). History isn't worth preserving — the on-disk charter violations were the entire output.

---

## Pre-execution checklist

Before starting Phase 1, confirm:

- [ ] Tree-shape decision locked (Option A or B). Plan assumes B; adjust paths if A.
- [ ] Charter cleanup applied (Section 2).
- [ ] All destructive operations (model deletion, extension replacement, old directory removal) approved.
- [ ] The smoke test from Phase 7 is understood as a plumbing test, not a routing test (Frame C remains open).

## Post-execution checklist

- [ ] New `~/prj/intraface/` exists with layout matching the locked tree shape
- [ ] Charter at `~/prj/intraface/docs/charter.md` with cleanup applied
- [ ] Spawn helper at `~/prj/intraface/lib/spawn-llama.ts` exports working functions
- [ ] Grammar ported to `~/prj/intraface/units/summarize/grammar.gbnf` with interim header
- [ ] Runtime registries at `~/.intraface/*.toml` with values matching cited commands
- [ ] Deployed extension at `~/.pi/agent/extensions/intraface.ts` (real file, absolute import)
- [ ] Old `~/.pi/agent/extensions/summarize.ts` removed
- [ ] End-to-end test passes: 9-10s wall, exit 0, valid JSON
- [ ] Old `~/prj/subagent-summarize/` directory removed
- [ ] Rejected model files deleted
- [ ] Git initialized locally; remote push deferred until `rtr/intraface` exists on Forgejo

## Open work after this plan

1. **Build the first charter-compliant Unit.** The current summarize shape fails Tests 1 and 2. Replace with extraction-shape: path-parameter, schema-with-provenance (text + quote + span), domain primer. Until this lands, Intraface has infrastructure but no charter-passing Unit.

2. **Resolve `-j` brokenness.** Either rebuild mainline llama.cpp with a fix, or wait for upstream. Revisit whether `grammars/` directory should exist.

3. **Frame C (router test).** Plumbing works; routing does not. The Core doesn't auto-invoke the tool under normal operation. Open design problem; do not solve prematurely.

4. **Migrate docs.** `features.md` and (parts of) `oversight-agent-prd.md` move to `~/prj/intraface/docs/` when Intraface is established. Out of scope for this plan.

5. **AGENTS.md for the new repo.** Should exist with link-directory marker blocks per cluster convention. Not in this plan; separate task.
