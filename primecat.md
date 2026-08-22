# Executor on Pipecat — Architecture

**Status:** drafting  
**Date:** 2025-08-13  
**Supersedes:** Pi (TypeScript) as Executor harness

## Decision

Replace Pi (TypeScript terminal agent) with Pipecat as the Executor runtime. The
charter's Core/Unit/Executor taxonomy, five tests, and four verbs are unchanged —
only the harness changes.

## Why

Pi is the wrong harness language for a model-serving substrate that is C/Python/HTTP
all the way down. The `extract.ts` failure was a symptom: a llama-cli subprocess
colliding with Pi's TUI at the TS→Python→llama.cpp boundary crossing. Vice already
proves Pipecat calls Core directly on this box. The prime-agent control layer gives
Pipecat the subagent isolation the charter's router test (test 3) demands.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Pipecat WorkerRunner                                │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  ExecutorWorker (root Pipecat worker)          │   │
│  │  - LLMService → Core :7712                    │   │
│  │  - FunctionCall handlers → Unit ports          │   │
│  │  - rlm() control module → spawn child workers │   │
│  │  - persistent Python state (harness)           │   │
│  └──────────┬───────────────────────────────────┘   │
│             │ WorkerBus                             │
│  ┌──────────┴───────────────────────────────────┐   │
│  │  Child workers (spawned by rlm())              │   │
│  │  - independent Pipecat PipelineWorkers         │   │
│  │  - own LLMContext, own function handlers       │   │
│  │  - bus messages back to parent                │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
        │                          │
        ▼                          ▼
  llama.cpp ports              herdr (later)
  :7712 Core                  terminal multiplexing
  :7713-:7719 Units           and cross-platform coord
```

### Mapping prime-agent → Pipecat

| Prime Agent (TS + IPython)        | Intraface (Pipecat)                     |
|------------------------------------|------------------------------------------|
| `AgentSession`                     | `PipelineWorker` (via `WorkerRunner`)    |
| `rlm.run(prompt)`                  | `rlm(prompt)` → spawn new worker         |
| IPython persistent kernel           | Pipecat's built-in function handlers     |
| Jupyter comm `host.request`        | WorkerBus pub/sub                        |
| `agent_message.send()`             | Bus message to parent worker             |
| Child registry in TS host           | `WorkerRegistry` on `WorkerRunner`       |
| `rlm.harness` state                 | Persistent JSON in session directory     |
| Python-backed skills                | Python packages in `skills/`             |

### Key simplification

Prime Agent couples the model to a persistent IPython kernel via Jupyter ZeroMQ.
We don't need that. Pipecat's `FunctionCallParams` already give us programmatic
tool calls. `rlm("review auth")` is a function call, not a kernel cell. The child
is a Pipecat `PipelineWorker`, not a Jupyter kernel. Results come via the bus,
not Jupyter comms.

## Unit function handlers

| Handler             | Port  | Purpose                            |
|---------------------|-------|------------------------------------|
| `unit_chat`         | :7713 | Instruct Q&A (warm unit)            |
| `unit_decide`       | :7714 | Binary/classification decisions    |
| `unit_decide_heavy` | :7715 | Escalated decisions (8B)            |
| `embed`             | :7716 | BGE-M3 embeddings (CLS, 1024-dim)  |
| `embed_colbert`     | :7717 | ColBERT per-token vectors           |
| `embed_lfm25`       | :7718 | LFM2.5 embeddings (CLS, 1024-dim)  |
| `encode`            | :7719 | MLM encoder (fill-mask)             |

## Implementation phases

### Phase 1: Foundation
1. Create `executor/` directory with Pipecat venv
2. Port Vice's `bot.py` pattern: `WorkerRunner` + `OpenAILLMService` → `:7712`
3. Wire Unit function handlers to `:7713`-`:7719`
4. Text transport (stdin/stdout or WebSocket, not WebRTC)
5. Smoke test: model calls a Unit handler

### Phase 2: rlm() subagent spawning
1. `rlm()` as a function handler that spawns child `PipelineWorker`s
2. Shared config inheritance, own LLMContext per child
3. Bus messages for child→parent results
4. Child registry and lifecycle

### Phase 3: Harness + Skills
1. Persistent harness state (JSON, not IPython)
2. Skill discovery (`SKILL.md` + importable Python)
3. Session persistence, daemon-backed workers

### Phase 4: Herdr integration
1. Herdr socket client for driving panes
2. Agent state reporting
3. Cross-platform coordination

## Starting point

Phase 1. The 80% head start is Vice's `bot.py` — swap voice transport for text,
add Unit function handlers.

## Potential edges (exploratory)

These are reasons to think specific choices might pay off. They are not claims.

### uv: per-worker dependency isolation

Prime Agent bootstraps one kernel venv with uv (Python 3.11, ipykernel,
prime-agent-runtime). Every skill, every child agent, shares that namespace.

uv gives us fast dependency management regardless. The question is isolation.

**Correction:** `WorkerRunner` runs added workers concurrently as asyncio tasks on
an in-process `AsyncQueueBus`. A child spawned by `rlm()` is *not* a separate
process by default. Per-worker venv isolation would require explicit process
isolation (subprocess per child), which is a separate design choice with real
costs — startup time, memory overhead, IPC complexity.

*Why it might matter:* If children are focused subtasks that need different
dependencies and true sandboxing, process isolation is worth the cost. If
children are lightweight function-call loops that share the parent's dependencies,
in-process workers are simpler and faster.

*Open question for Phase 2:* Does the Executor need child process isolation, or is
in-process concurrency sufficient?

### Podman: container isolation for child workers

This is the concrete answer to the isolation question above. Podman (rootless)
gives each `rlm()` child a real sandbox — its own filesystem, its own process
tree, its own network namespace — while the parent controls it from Python via
`podman-py`.

`podman-py` is a Python binding to Podman's REST API. From the Executor, a child
spawn looks like:

```python
import podman
with podman.PodmanClient() as client:
    container = client.containers.run(
        "localhost/primecat-worker:latest",
        detach=True,
        environment={"TASK": prompt, "PARENT_SOCKET": socket_path},
        mounts=[...session_dir...],
    )
    # child runs, reports back via socket/bus, parent collects result
    container.wait()
    logs = container.logs()
    container.remove()
```

Podman is rootless, daemonless, and OCI-compatible. No Docker, no dockerd.
Containers are just cgroups + namespaces managed by a user-level socket.

*Why it might matter:*

- Solves the isolation question that Vice flagged: if Phase 2 reveals children
  need real process separation, Podman gives it without a custom subprocess
  manager. Each child gets its own venv baked into the image.
- Charter compliance: the `Act` verb (gated by the PRD) is "what may change
  the machine." A container that can only write to its own mount and only
  reach the inference endpoints is a natural act boundary. The host filesystem
  is not exposed unless explicitly mounted.
- Skills become container images. A PDF-processing skill is an image with
  Kreuzberg baked in. A code-review skill is an image with the repo tools.
  No shared dependency conflicts. uv builds the images.

*Why it might not:*

- Startup latency. Container create+start is ~100-500ms on a warm image cache.
  An in-process `PipelineWorker` spawns in microseconds. If children are
  lightweight (single function-call loop, no sandboxing needed), the overhead
  is wasted. If children are long-running (code review, document extraction), the
  overhead is negligible.
- GPU access from rootless Podman is possible but non-trivial. Our Core on `:7712`
  is GPU-backed. A containerized child calling `:7712` over HTTP doesn't need
  GPU passthrough (it's just an HTTP client), but a child that needs its own
  GPU model would need `--device /dev/dri` or NVIDIA container toolkit.
- We don't have Podman installed yet. It's a new dependency with its own
  lifecycle (socket activation, image builds, storage management). Another
  thing to operate.
- IPC from container to parent Pipecat bus is not trivial. The container is
  a separate process with its own network namespace. Communication back to
  the parent's `WorkerBus` requires either a Unix socket mount, HTTP callback,
  or shared queue. This is a design problem, not a dealbreaker, but it's real
  work.

*What would prove it:* Start Phase 2 with in-process workers. If concrete tasks
  surface where children need isolation — untrusted code, conflicting
  dependencies, act-boundary enforcement — then add Podman for those specific
  children. In-process for the default, containers for the exceptional.

### Kreuzberg + SurrealDB as executor session/scratch state

Prime Agent uses IPython's in-memory namespace as the model's scratchpad.
Variables, imports, parsed results survive across turns. State is serialized to
`.dill` (pickled Python objects) for session persistence and `.json` for
harness metadata.

An alternative: Kreuzberg extracts any document (91+ formats, native Rust) into
structured text. That text gets embedded via the Unit ports and stored in
SurrealDB. The agent's scratch state is a database, not a Python namespace.

**Boundary condition:** This is a separate bounded context from Vice Memory.
If executor content later enters Vice Memory, it must go through the
Exchange → Candidate → Candidate Decision flow — never direct writes to Vice's
`memory_entry`, Candidate, or retrieval tables. Executor child output is
Assistant Proposal, never Authority. Document extraction is Tool Observation,
not automatically a Memory Record.

*Why it might matter:*

- `.dill` is a fragile pickle of arbitrary Python objects. It breaks across
  Python version changes, can't be inspected without loading it, and can't
  be queried — you get the whole namespace or nothing. SurrealDB records are
  queryable, auditable, and survive process restarts without deserialization.
- Kreuzberg handles the charter's ungated `See` verb: the agent encounters a
  PDF, `.docx`, `.xlsx`, email, or `.ipynb` and extracts it to structured
  text without the Core ever touching the raw binary. The reduction happens
  before it reaches context, which is the charter's attention test.
- Cross-session recall: a fact extracted in session 1 is available in session
  3 without serializing and deserializing a Python kernel state. Vice's
  memory system already proves this path works (SurrealDB + BGE-M3 embeddings).

*Why it might not:*

- A Python namespace lets the model do `df.head()`, inspect intermediate
  results, iterate interactively. A database is not a REPL. The question is
  whether Pipecat's function handlers give enough interactive scratchpad
  without needing IPython, or whether some tasks genuinely need live Python
  objects in memory and nothing else will do.
- Serialization of Python objects to database records is lossy. A pandas
  DataFrame with complex index state, a parsed AST, a live network connection —
  these don't have clean SurrealDB representations. If the model's workflow
  depends on these, the database model is a downgrade.
- This is unproven territory. Prime Agent's kernel approach is battle-tested;
  replacing it with Kreuzberg+SurrealDB is a bet that structured storage beats
  in-memory objects for agent working state. It might, but it might also turn
  out that agents need both — a scratchpad for live computation and a database
  for durable memory.

*What would prove it:* Build Phases 1–2 without Kreuzberg/SurrealDB (no memory
dependency). Preserve session/worker/provenance IDs so future evidence remains
attributable. At Phase 3, decide separately whether Primecat needs ephemeral
Python scratch state, durable executor state, Vice semantic memory, or some
combination. If Kreuzberg extraction surfaces as genuinely useful for concrete
tasks, it gets its own schema — not reuse of Vice's tables.
