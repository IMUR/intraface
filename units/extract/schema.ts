// schema.ts — single source of truth for the extract specialist's types.
//
// Two distinct concerns live here:
//
//   1. TypeScript types (ModelOutput, ModelItem, VerifiedItem, ExtractResult,
//      Span, Provenance) — the TS source of truth. Always authoritative.
//
//   2. MODEL_OUTPUT_SCHEMA — the JSON Schema object that *would* be passed
//      to `llama-cli --json-schema` if that flag worked.
//
// IMPORTANT (2026-07-06): `--json-schema`/`-j` is BROKEN on mainline llama.cpp
// build 9861 (c8ae9a750) — sampler init throws "Failed to initialize samplers:
// std::exception". The runtime enforcement mechanism is therefore NOT this
// file's MODEL_OUTPUT_SCHEMA; it is `grammar.gbnf`, hand-maintained alongside
// `extract.ts`. MODEL_OUTPUT_SCHEMA is **documentation only** — it records the
// shape the JSON Schema would have, kept here so that when upstream fixes
// `--json-schema`, the runtime path can be switched back by passing this
// object instead of `--grammar-file`.
//
// The hand-sync obligation this creates: when the TS types change,
// MODEL_OUTPUT_SCHEMA *and* grammar.gbnf must both be updated to match.
// That manual sync is the one piece of debt the fallback introduces.
//
// Zero dependencies on purpose: this file must load under
// `node --experimental-strip-types` from the project directory without an
// install step. (Folding these types into TypeBox is a Phase-B nicety once
// the workspace owns its dependency manifest.)

// ---------- What the model is asked to emit ----------

export interface ModelItem {
  /** The model's restatement of the claim. */
  text: string;
  /** VERBATIM text copied from the source. Verified by string match after parse. */
  quote: string;
}

export interface ModelOutput {
  /** Abstractive digest, <= 3 sentences. NOT verified — convenience only. */
  summary: string;
  key_points: ModelItem[];
  decisions: ModelItem[];
  action_items: ModelItem[];
  open_questions: ModelItem[];
}

// Documentation-only JSON Schema. See file header.
// Not passed to any runtime consumer today; grammar.gbnf is the enforcement.
const ITEM_SCHEMA = {
  type: "object",
  properties: {
    text: { type: "string" },
    quote: { type: "string" },
  },
  required: ["text", "quote"],
} as const;

export const MODEL_OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    summary: { type: "string" },
    key_points: { type: "array", items: ITEM_SCHEMA },
    decisions: { type: "array", items: ITEM_SCHEMA },
    action_items: { type: "array", items: ITEM_SCHEMA },
    open_questions: { type: "array", items: ITEM_SCHEMA },
  },
  required: ["summary", "key_points", "decisions", "action_items", "open_questions"],
} as const;

// ---------- What the specialist actually returns (post-verification) ----------

export interface Span {
  /** 1-indexed, inclusive, in ORIGINAL file coordinates (range-aware). */
  start_line: number;
  end_line: number;
}

export interface VerifiedItem extends ModelItem {
  /** Located span of the quote, or null if the quote could not be found. */
  span: Span | null;
  /** true = quote confirmed against source (exact or whitespace-normalized). */
  verified: boolean;
}

export interface Provenance {
  path: string;
  start_line: number;
  end_line: number;
  /** sha256 of the exact bytes extracted (the slice, not the whole file). */
  content_sha256: string;
  /** ISO-8601 timestamp of the run. */
  moment: string;
  /** Which specialist produced this, and on what substrate. */
  executor: string;
}

export interface ExtractResult {
  summary: string; // unverified digest
  key_points: VerifiedItem[];
  decisions: VerifiedItem[];
  action_items: VerifiedItem[];
  open_questions: VerifiedItem[];
  provenance: Provenance;
  verification: {
    total_items: number;
    verified: number;
    unverified: number;
  };
}
