# Local Specialist — Feature Backlog

**Purpose:** Track observed token-hungry patterns in Pi's orchestrator
behavior and map them to potential local-specialist capabilities. Each
entry is an observation, not a commitment — features ship when the
pattern recurs often enough to justify the build.

**Architecture context:** All features assume the same subprocess
pattern proven in the `summarize` slice (spawn llama-cli + LFM2.5-1.2B
+ grammar-file + JSON.parse, CPU-only, 60s timeout, no shell wrappers).
A new feature = new prompt + new grammar + new tool registration, not
new infrastructure.

---

## Tier 1 — High-frequency, high-signal-ratio, local-only

These ship soonest. Each recurs multiple times per session and bleeds
context for low reasoning value.

### transcript-state
**Trigger:** "What is the dev agent doing right now?"
**Shape:** Read a terminal tail (50-500 lines), extract: current
command, recent failures, open decisions, blocked state. Return as
structured JSON.
**Why local:** No external lookup needed. LFM2.5 has the right shape
for "noisy log → clean struct." Today's oversight session read multiple
terminal tails in full to answer this question.
**Output schema:** `{current_command, last_exit_code, failures[], open_questions[], state}`

### find-matching-file
**Trigger:** "Give me a representative X" / "find a long code file" /
"show me a Pi extension example"
**Shape:** Pure shell — `find` with criteria, return paths only. No
LLM work. Today Pi spent 5 round-trips and read 3 `ls` outputs to pick
one test file.
**Why local:** No LLM needed. This is a Pi-hygiene fix disguised as a
specialist. Could also just be a rule change ("don't read ls output to
find a file"), but a tool with a clear contract is more reliable than
prompting alone.
**Output schema:** `{paths[], count, criteria}`

### doc-section-lookup
**Trigger:** "Does llama-cli have a flag for X?" / "what does
AGENTS.md say about Y?"
**Shape:** Read full doc, return only the section matching the query.
Today's session read a 525-line `--help` output to find 3 relevant
lines. Ratio 175:1.
**Why local:** Same engine, same subprocess, different prompt. Needs a
focused-answer grammar (output is text, not structured object).
**Output schema:** `{section_heading, content, line_range}` or plain text

---

## Tier 2 — Medium-frequency, needs infrastructure

Worth building once Tier 1 is stable. Each needs something beyond a
prompt+grammar.

### cached-digest
**Trigger:** Re-reading a file already summarized in a prior session
**Shape:** Persistent index of `{file_hash, digest, summarized_at}`.
On summarize call, check index first; return cached digest if hash
matches. Falls back to fresh summarize on miss.
**Why local:** Needs an index file or small DB. The LLM work is the
same as `summarize`; the new piece is cache management.
**Output schema:** Same as summarize, plus cache metadata

### verify-claim
**Trigger:** "Is X still true?" / "does the canon match reality?"
**Shape:** Take a claim + a list of sources, check each source for
confirming/refuting evidence, return pass/fail per source.
**Why local:** Judgment-heavy. May be too hard for LFM2.5; might need
a larger model or a different approach (rule-based checks first, LLM
for ambiguous cases).
**Output schema:** `{claim, verdict, evidence_per_source[], conflicts[]}`

---

## Tier 3 — Speculative

Patterns that have appeared once or twice but aren't yet clearly
worth a build. Track for recurrence.

### noisy-output-structurer
**Trigger:** Tool output explosions (the 12M-line spinner capture, the
53GB orphan output). Today these were handled by killing the process
and trying again; a specialist that could extract signal from a
truncated dump might recover some value.
**Open question:** Does this recur often enough to justify a tool, or
is "don't generate noisy output in the first place" the right fix?

### multi-source-distill
**Trigger:** Cross-referencing canon + operations + AGENTS.md to
answer a topology question.
**Open question:** Probably needs RAG infrastructure to be useful
beyond 2-3 sources. May not be local-specialist-shaped at all.

---

## Cross-cutting needs (not features, but blockers)

### Domain context for the specialist
**Observed 2026-07-03:** LFM2.5-1.2B has no domain knowledge. On
`rtr-cluster.md`, it expanded "rtr" as "Remote Transfer Service"
(actual: "Reactor rtr Cluster"). This will recur on every source
containing cluster proper nouns (prtr, drtr, crtr, trtr, OpenFang,
GLM, ik_llama, etc.).

**Fix layers, in order of cost:**
1. **System prompt primer** — 1-paragraph domain intro prepended to
   every prompt. Cheap, immediate. Probably kills 80% of hallucinations.
2. **Persistent context file** — `~/.pi/agent/extensions/context/
   specialist-context.md` read on every invocation. Domain terms,
   naming conventions, recurring proper nouns.
3. **Fine-tuning** — train the terms into the model. Premature until
   system-prompt primer is proven insufficient.

**Status:** Blocking eval quality. Address before declaring Phase 4
complete.

### Tool-use reliability (Frame C)
**Observed 2026-07-03:** The orchestrator LLM (GLM) does not auto-call
the registered `summarize` tool. When asked generically to "summarize
X," it summarizes directly using its own context. The tool is only
invoked when explicitly instructed ("use the summarize tool, do not
summarize yourself"). Worse: under friction (timeouts, parse errors),
the orchestrator offers to bypass the tool and do the work itself.

**Implication:** Registration alone is not enough to make offloading
seamless. The system-prompt hint the plan doc relied on is probably
insufficient. Open design problem — not a coding task.

**Status:** Frame C goal is unsolved. Defer until Phase 4 baseline
establishes whether the specialist's output is worth routing to at all.

---

## Adding to this doc

When you observe a new token-hungry pattern in any agent session:
1. Note the trigger (what the agent was trying to do)
2. Note the shape (input → desired output)
3. Note the token cost (rough ratio of tokens-in to signal-out)
4. Add to the appropriate tier, or to a new "observed once" section

Tier promotion: move from Tier 3 → Tier 2 → Tier 1 as recurrence
increases. Don't build until a pattern appears at least 3 times.
