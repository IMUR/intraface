// extract.ts — grounded extraction specialist (replaces summarize.ts).
//
// Contract: takes a PATH (never content), reads the source itself, runs the
// local SLM under a schema-derived grammar, then verifies every quote against
// the source by string match and computes line spans in code. The orchestrator
// never sees the bulk; what it gets back carries its own proof.
//
// CLI: node --experimental-strip-types extract.ts <file> [start_line] [end_line]

import { fileURLToPath } from "node:url";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import {
  type ModelOutput,
  type ModelItem,
  type VerifiedItem,
  type ExtractResult,
  type Span,
} from "./schema.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Default: the canonical Intraface custody location for this Unit's model.
// Override per-call via SPECIALIST_MODEL_PATH for testing or staging alternates.
const MODEL_PATH =
  process.env.SPECIALIST_MODEL_PATH ??
  path.join(
    os.homedir(),
    ".intraface",
    "models",
    "unit",
    "lfm2.5-1.2b-instruct",
    "LFM2.5-1.2B-Instruct-Q4_K_M.gguf",
  );
const LLAMA_CLI = process.env.LLAMA_CLI ?? "llama-cli";

// ---- Budget & timing constants ------------------------------------------
// LFM2.5 context ceiling.
const MODEL_CTX = 32768;
// Extraction output budget. 4000 was never finishable; ~700 is ample for
// grounded items and fits the timeout math below.
const N_PREDICT = 700;
// Conservative chars-per-token for logs/transcripts (denser than prose).
const CHARS_PER_TOKEN = 3.5;
// UNMEASURED conservative estimates for CPU inference on the 9900X.
// TODO(first run): replace with llama-bench numbers:
//   llama-bench -m <model> -p 8192 -n 128 -ngl 0
const PREFILL_TPS = 120;
const DECODE_TPS = 20;
const LOAD_OVERHEAD_S = 20; // model load + process spawn slack (cold start)
const TIMEOUT_CAP_MS = 600_000;

const approxTokens = (s: string) => Math.ceil(s.length / CHARS_PER_TOKEN);

// ---- Domain primer (features.md cross-cutting blocker #1) ----------------
// Layer-1 fix: inline system-prompt primer. Graduates to ~/.intraface config
// when that directory exists; keep it short — every token here is paid per call
// under the current per-call spawn model.
const PRIMER = `Context for proper nouns in the source: "rtr" is a private home-lab cluster (nodes: crtr, drtr, wrtr, prtr — prtr is "projector"). Pi is a terminal coding agent. GLM-4.7-Flash is a local LLM served by ik_llama.cpp. llama.cpp serves local specialist models (LFM2.5). Protext is a memory system; Intraface is the local reasoning architecture. OpenFang, OpenClaw, herdr, XTDB, SurrealDB, Forgejo are local tools/services. Treat all of these as proper nouns; never expand them into unrelated meanings.`;

const INSTRUCTIONS = `Extract from the source below. Respond with JSON only, matching the required schema.
Rules:
- Every item's "quote" must be VERBATIM text copied from the source, 200 characters or fewer.
- "text" is your own concise restatement of what the quote establishes.
- "summary" is at most 3 sentences.
- Use empty arrays for categories with nothing to report.
- Never invent content that is not in the source.`;

// ---- Quote location (spans are COMPUTED, never asked of the model) --------

function spanFromCharRange(
  content: string,
  a: number,
  b: number,
  lineOffset: number,
): Span {
  const startLine = lineOffset + content.slice(0, a).split("\n").length;
  const inner = content.slice(a, b);
  const endLine = startLine + inner.split("\n").length - 1;
  return { start_line: startLine, end_line: endLine };
}

function locateQuote(
  quote: string,
  content: string,
  lineOffset: number,
): { span: Span | null; verified: boolean } {
  // Pass 1: exact match.
  const idx = content.indexOf(quote);
  if (idx !== -1) {
    return {
      span: spanFromCharRange(content, idx, idx + quote.length, lineOffset),
      verified: true,
    };
  }
  // Pass 2: whitespace-normalized match (models mangle spacing, rarely words).
  const strip = (s: string) => s.replace(/\s+/g, "");
  const sq = strip(quote);
  if (sq.length === 0) return { span: null, verified: false };
  const lines = content.split("\n");
  const cum: number[] = [];
  let acc = 0;
  for (const line of lines) {
    acc += strip(line).length;
    cum.push(acc);
  }
  const joined = lines.map(strip).join("");
  const sIdx = joined.indexOf(sq);
  if (sIdx === -1) return { span: null, verified: false };
  const firstLine = cum.findIndex((c) => c > sIdx);
  let lastLine = cum.findIndex((c) => c >= sIdx + sq.length);
  if (lastLine === -1) lastLine = lines.length - 1;
  return {
    span: {
      start_line: lineOffset + firstLine + 1,
      end_line: lineOffset + lastLine + 1,
    },
    verified: true,
  };
}

function verifyItems(
  items: ModelItem[],
  content: string,
  lineOffset: number,
): VerifiedItem[] {
  return items.map((it) => {
    const { span, verified } = locateQuote(it.quote ?? "", content, lineOffset);
    return { text: it.text, quote: it.quote, span, verified };
  });
}

// ---- Main entry ------------------------------------------------------------

export async function extract(
  filePath: string,
  startLine?: number,
  endLine?: number,
): Promise<ExtractResult> {
  const resolved = path.resolve(filePath);
  if (!fs.existsSync(resolved)) {
    throw new Error(`extract: no such file: ${resolved}`);
  }
  const raw = fs.readFileSync(resolved, "utf8");
  const allLines = raw.split("\n");

  const from = Math.max(1, startLine ?? 1);
  const to = Math.min(allLines.length, endLine ?? allLines.length);
  if (from > to) {
    throw new Error(`extract: empty range ${from}-${to} for ${resolved}`);
  }
  const content = allLines.slice(from - 1, to).join("\n");
  const lineOffset = from - 1; // spans reported in original-file coordinates

  // ---- Budget check (defect #2: no silent truncation, ever) ----
  const header = `SOURCE (lines ${from}-${to} of ${resolved}):`;
  const prompt = `${PRIMER}\n\n${INSTRUCTIONS}\n\n${header}\n"""\n${content}\n"""`;
  const promptTokens = approxTokens(prompt);
  const budget = MODEL_CTX - N_PREDICT - 256;
  if (promptTokens > budget) {
    const err: any = new Error(
      `extract: input too large (~${promptTokens} tokens; budget ${budget}). ` +
        `Pass start_line/end_line to select a slice of ${resolved} ` +
        `(${allLines.length} lines total).`,
    );
    err.code = "input_too_large";
    err.details = { estimated_tokens: promptTokens, budget, total_lines: allLines.length };
    throw err;
  }

  // ---- Derived runtime parameters (defect #3: math that closes) ----
  const ctx = Math.min(MODEL_CTX, Math.ceil((promptTokens + N_PREDICT + 256) / 512) * 512);
  const timeoutMs = Math.min(
    TIMEOUT_CAP_MS,
    Math.ceil((promptTokens / PREFILL_TPS + N_PREDICT / DECODE_TPS + LOAD_OVERHEAD_S) * 1000),
  );

  // NOTE (2026-07-06): -j/--json-schema throws on this build's sampler init
  // ("Failed to initialize samplers: std::exception") — confirmed via direct
  // repro on mainline 9861 (c8ae9a750). Falling back to --grammar-file until
  // upstream fixes it. This means grammar.gbnf (hand-maintained, alongside
  // this file) is the runtime enforcement mechanism, NOT the JSON Schema
  // exported by schema.ts — schema.ts's types are the TS source of truth, but
  // its MODEL_OUTPUT_SCHEMA object is documentation only and does not drive
  // runtime constraint. Keep grammar.gbnf and schema.ts's MODEL_OUTPUT_SCHEMA
  // in sync by hand; that sync is the one piece of debt this fallback
  // introduces. Revisit when llama.cpp updates.
  const args = [
    "-m", MODEL_PATH,
    "-c", String(ctx),
    "-n", String(N_PREDICT),
    "-ngl", "0",
    "-st",
    "--log-disable",
    "--no-display-prompt",
    "--grammar-file", path.join(__dirname, "grammar.gbnf"),
    "-p", prompt,
  ];

  const stdout = await runLlama(args, timeoutMs);

  const jsonMatch = stdout.trim().match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    throw new Error(`extract: no JSON in model output:\n${stdout.slice(0, 2000)}`);
  }
  const parsed: ModelOutput = JSON.parse(jsonMatch[0]);

  // ---- Verification (defect #4: proof, computed in code) ----
  const key_points = verifyItems(parsed.key_points ?? [], content, lineOffset);
  const decisions = verifyItems(parsed.decisions ?? [], content, lineOffset);
  const action_items = verifyItems(parsed.action_items ?? [], content, lineOffset);
  const open_questions = verifyItems(parsed.open_questions ?? [], content, lineOffset);
  const all = [...key_points, ...decisions, ...action_items, ...open_questions];
  const verifiedCount = all.filter((i) => i.verified).length;

  return {
    summary: parsed.summary ?? "",
    key_points,
    decisions,
    action_items,
    open_questions,
    provenance: {
      path: resolved,
      start_line: from,
      end_line: to,
      content_sha256: createHash("sha256").update(content).digest("hex"),
      moment: new Date().toISOString(),
      executor: "extract@LFM2.5-1.2B-Instruct-Q4_K_M/llama-cli-cpu",
    },
    verification: {
      total_items: all.length,
      verified: verifiedCount,
      unverified: all.length - verifiedCount,
    },
  };
}

function runLlama(args: string[], timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(LLAMA_CLI, args, {
      env: { ...process.env, CUDA_VISIBLE_DEVICES: "" }, // GPU discipline: kept
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (c) => (stdout += c.toString()));
    child.stderr.on("data", (c) => (stderr += c.toString()));

    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(
        new Error(
          `extract: llama-cli timeout after ${Math.round(timeoutMs / 1000)}s ` +
            `(computed from input size — if this fires, update PREFILL_TPS/DECODE_TPS ` +
            `from llama-bench)\nSTDERR tail: ${stderr.slice(-1500)}`,
        ),
      );
    }, timeoutMs);

    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(`extract: llama-cli exit ${code}\nSTDERR tail: ${stderr.slice(-1500)}`));
        return;
      }
      resolve(stdout);
    });

    child.on("error", (e) => {
      clearTimeout(timer);
      reject(new Error(`extract: spawn error: ${e}`));
    });
  });
}

// ---- CLI entry -------------------------------------------------------------
if (import.meta.url === `file://${process.argv[1]}` && process.argv[2]) {
  const [, , file, s, e] = process.argv;
  extract(file, s ? parseInt(s, 10) : undefined, e ? parseInt(e, 10) : undefined)
    .then((r) => console.log(JSON.stringify(r, null, 2)))
    .catch((err) => {
      console.error("Error:", err.message);
      process.exit(1);
    });
}
