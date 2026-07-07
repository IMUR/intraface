---
title: "The Intraface Charter"
date: 2026-07-05
status: locked concept
authority: charter — describes the conceptual model. Implementation details
  (engines, transports, ports, models, directory names) are deliberately
  absent and may change freely. A change that would require editing this file
  is architectural, and must be made deliberately — never by drift.
---

# Intraface — Charter

## Core concept

One machine, one Executor. The Executor's core — its resident model's context window — is the scarcest resource on the box: expensive to hold, and degrading in quality as it fills.

**Intraface is the discipline of ensuring expensive attention is never spent on what cheaper attention can do and prove.**

The pattern is recursive:

- **Units** (external experts — small models, each with its own fixed model and its own context window) spend cheap attention reading bulk so the Core never has to.
- **The Core** spends its context verifying, reconciling, and gating so the human never has to.
- **The human** is the apex — the most expensive attention in the system, and the final judge.

Each level owes the level above it the same contract: a small, provable output in place of a large, raw one. Oversight's reporting rules ("short by default; cite or retract; lead with the conclusion") are this contract at the top tier. Schema-plus-span outputs are the same contract at the bottom tier.

This is why the mixture-of-experts framing is identity, not metaphor: the Core routes internally among experts in its own weights; the Executor routes externally among Units beside it. In both cases the **router, never the expert, decides what fires.** Unlike theories of emergent or competitive access, nothing in this architecture wins its own way in — access is always decided by policy, never by salience. (A deeper cognitive-science framing for the Executor/Protext pair taken together, rather than for either alone, may exist; that is a question for a future document, not this charter.)

The one-box constraint is a feature. Abundance lets architectures get sloppy; a fixed budget makes every token accountable, and that accountability forces the verifiability the whole system's trust rests on.

## Taxonomy

- **Executor** — the whole system: Core, Units, and the routing between them. The system's identity.
- **Core** — the single resident model (today: GLM-4.7-Flash). One per Executor. Its current functional role toward the human is *oversight agent* — a role, not a second name for the system. If the Core ever took on a different or additional role, "Core" would not need to change; only its role would.
- **Unit** — a model-backed external expert Core routes work to. Each Unit has a model, fixed deliberately (not incidental) — different Units may use different models or share one. A Unit's context window is its model's context window: small, disposable, non-competing with the Core's.

**Deliberately unnamed:** Core may at some point also route to non-model mechanical work (shell commands, deterministic checks) that has no model and no context window. This is not a Unit and has no name yet. It is not part of this taxonomy today — naming it before a real case exists would risk fitting the name to a guess rather than to shape. When a real case arrives, it earns its own term then.

## Four verbs, three gates

The Executor exists within the machine, not within a harness. Governance is placed by verb:

- **See — ungated.** Perception is native: files, /proc, ports, live state, unmediated. A Core whose perception passes through a transforming layer observes the layer, not the machine, and can never satisfy D1 ("cited command + observed output"). Native perception is a requirement of the oversight role, not a universal claim — Units may remain contained; the Core may not be.
- **Attend — gated by this charter.** What may enter the Core's context, and in what shape: the five tests.
- **Remember — gated by Protext.** What may persist, and with what provenance: the Formation Gate.
- **Act — gated by the PRD.** What may change the machine: the decision-authority table.

Workspace-centric platforms collapse all four verbs into one wall at "see." Intraface walls the last three and leaves the first native — which is what lets the Core exist pragmatically while remaining fully auditable. Provenance is context.

## The sibling system: Protext

**Intraface makes trust cheap in the moment; Protext makes trust survive time.** Intraface governs attention — transit, in the moment, into the Core's context. Protext governs memory — persistence, across time. They meet at exactly Protext's two client boundaries, because Intraface is a client of Protext:

- **Perception-side joint.** The Core's context is ephemeral. Anything it intends to outlive the session is submitted as a Perception through the Formation Gate; nothing is remembered by another path. The Unit proof shape — text, quote, span, source, hash, moment, executor — is already the Gate's admission shape: proof-at-transit becomes provenance-at-rest without translation.
- **Delivery-side joint.** Context served back from memory enters the Core's context like any other input: reduced and lineage-cited, subject to the attention and proof tests. Nothing is exempt for being "our own memory."

Perception and Delivery are Protext's sensory and motor boundaries; Reflection is its background consolidation; the Memory tier stages what the Core will next attend to.

Deployment sequencing — including whether an interim store carries oversight testimony until Protext is resident on the node — is an operational question outside this charter.

## The five tests

Every proposal — new Unit, new tool, refactor, research idea, agent suggestion — must pass these. **They are questions about shape, not technology.** Applying them requires no expertise in the underlying stack. If a proposal fails one, the burden of proof is on the proposal.

### 1. The attention test
*Does this reduce what the Core's context must hold, or grow it?*
Anything that puts more into the Core's context — or demands more of the human's attention — needs extraordinary justification.
**Precedent:** the original `summarize` tool took source *text* as its parameter; the full bulk transited the Core's context twice before any saving occurred. Failed this test. Catching it required zero code knowledge.

### 2. The proof test
*Does the output carry its own verification — schema validity, quotes with spans, exit codes, cited commands — such that checking is cheaper than redoing?*
"Trust me" outputs are inadmissible at every tier. This is oversight decision D1, extended downward to machines.
**Precedent:** the first grammar enforced structure but no provenance; outputs couldn't be trusted without re-reading the source, making the offload worthless. Schema v2 (text + quote + span) exists because of this test.

### 3. The router test
*Who decides this runs — mechanical policy, or the Core's own judgment?*
Never ask the expert to gate itself. A design that relies on the Core choosing to protect its own context will fail.
**Precedent:** Frame C, observed in the field — the Core declined to call a registered Unit, and under friction offered to bypass it and do the work itself. The research literature and every surveyed production harness reached the same conclusion independently.

### 4. The substrate test
*Is the cheapest sufficient worker doing the job?*
Code before small model; small model before Core; Core before human. Using the Core's context where a mechanical check would suffice fails downward; asking a small Unit for judgment it can't support fails upward.

### 5. The custody test
*Does this thing have exactly one owner, with everything else holding a reference?*
Deletion is the probe: removing a directory should break nothing outside its custody. Conceptual membership (what the Executor *includes*) is broader than filesystem custody (what it *owns*).
**Precedent:** the Unit model weights got Intraface custody (single-purpose, single-consumer); `~/.pi` stayed a respected sibling; the original project directory's accretion happened precisely because incubating work had no owned home.

## What Intraface is not

- Not a framework or a product. It is a discipline applied to one deployment.
- Not multi-agent for its own sake. A Unit exists only where a test-passing reduction exists.
- Not attached to any engine, transport, model, or path. Those are current choices, not identity.
- Not a system that grows its own authority. What counts as success — the human doing less, or the human's attention counting for more — is already answered by the PRD's D6: scope is never expanded by the system on its own; gaps are surfaced, and the human decides. Intraface does not choose its own leash.

## How to use this document

When a proposal arrives — from any agent, any chat, any paper — run the five tests. Passing all five doesn't guarantee correctness; failing one means the proposal must argue for an exception explicitly. This converts expertise asymmetry into a fair fight: technical claims can't be argued past you, and shape can't be hidden from you.

Companion documents, per D5 (documents don't blur roles): the oversight PRD specifies behavior; the Protext charter holds the sibling doctrine of memory; this charter holds the concept of attention and the Executor/Core/Unit taxonomy. Drift between any of them is itself a finding.