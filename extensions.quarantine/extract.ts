// extensions/pi/extract.ts — Pi shim for the extract Unit.
//
// Deploy to ~/.pi/agent/extensions/extract.ts (replacing the old summarize.ts
// registration once this is verified end-to-end).
//
// This file is intentionally thin: it contains zero domain logic. It only
// adapts Pi's tool-registration API to the plain TypeScript function exported
// by the extract Unit. All extraction, verification, and provenance work lives
// in the Unit at units/extract/extract.ts.
//
// The description below is doing real work: tool-selection research says the
// docstring drives invocation, so it states when to use it, when not to, and
// names the anti-pattern (pasting content) explicitly.

import { Type } from "typebox";
import { extract } from "/home/prtr/prj/intraface/units/extract/extract.ts";

export default function (pi: any) {
  pi.registerTool({
    name: "extract",
    label: "Extract (grounded)",
    description:
      "Extract grounded facts from a file WITHOUT reading it into your own context. " +
      "Pass a path (plus optional line range); returns key points, decisions, action " +
      "items, and open questions — each with a verbatim quote and a verified line span, " +
      "plus provenance (sha256, range, timestamp). Use this INSTEAD of reading any " +
      "file, log, or transcript longer than ~200 lines when you need its substance " +
      "rather than its exact full text.",
    promptSnippet:
      "Grounded extraction from files by path — returns verified, quoted claims instead of raw content",
    promptGuidelines: [
      "Prefer extract over reading a file when it exceeds ~200 lines and you need understanding, not verbatim content.",
      "Always pass a path. Never paste file contents as an argument.",
      "Items with verified:true carry quotes confirmed against the source; treat verified:false items as unconfirmed claims.",
      "If the tool reports input_too_large, call it again with start_line/end_line slices instead of reading the file yourself.",
    ],
    parameters: Type.Object({
      path: Type.String({ description: "Absolute path to the source file" }),
      start_line: Type.Optional(
        Type.Integer({ minimum: 1, description: "First line of slice (1-indexed, inclusive)" }),
      ),
      end_line: Type.Optional(
        Type.Integer({ minimum: 1, description: "Last line of slice (1-indexed, inclusive)" }),
      ),
    }),
    async execute(_toolCallId: string, params: any, _signal: any, _onUpdate: any, _ctx: any) {
      const result = await extract(params.path, params.start_line, params.end_line);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: {},
      };
    },
  });
}
