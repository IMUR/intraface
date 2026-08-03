import {
  usePipecatConversation,
  type ConversationMessage,
} from "@pipecat-ai/voice-ui-kit";
import { usePipecatClient } from "@pipecat-ai/client-react";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";

/**
 * Bridge: Pipecat RTVI conversation events → assistant-ui external store.
 *
 * `usePipecatConversation` aggregates the RTVI event stream (user-transcription,
 * bot-output) into ConversationMessage objects with streaming updates. We feed
 * those verbatim into assistant-ui's external-store runtime, which owns
 * rendering, autoscroll, and run status. No state is duplicated here.
 *
 * Typed input flows back over RTVI `send-text` (handled server-side by the
 * auto-created RTVIProcessor): the composer submits → optimistic user message
 * via injectMessage → client.sendText(). The bot answers in voice + transcript.
 */

function partText(text: unknown): string {
  if (typeof text === "string") return text;
  if (text && typeof text === "object") {
    const t = text as { spoken?: string; unspoken?: string };
    if ("spoken" in t || "unspoken" in t) return (t.spoken ?? "") + (t.unspoken ?? "");
  }
  return "";
}

function toThreadMessage(m: ConversationMessage): ThreadMessageLike {
  const text = m.parts.map((p) => partText(p.text)).join("");
  return {
    id: `${m.role}:${m.createdAt}`,
    role: m.role === "user" ? "user" : "assistant",
    content: [{ type: "text", text }],
    createdAt: new Date(m.createdAt),
  };
}

function appendMessageText(message: AppendMessage): string {
  return message.content
    .filter((p) => p.type === "text")
    .map((p) => p.text)
    .join("")
    .trim();
}

export function ConversationThread() {
  const client = usePipecatClient();
  const { messages, injectMessage } = usePipecatConversation();

  // function_call / system messages are not conversational turns.
  const turns = messages.filter((m) => m.role === "user" || m.role === "assistant");
  const last = turns.at(-1);
  const isRunning = !!last && last.role === "assistant" && last.final === false;

  const runtime = useExternalStoreRuntime<ConversationMessage>({
    messages: turns,
    isRunning,
    convertMessage: toThreadMessage,
    onNew: async (message) => {
      const text = appendMessageText(message);
      if (!text || !client) return;
      // Optimistic echo: the server processes send-text without re-emitting
      // it as a user transcription.
      injectMessage({
        role: "user",
        parts: [{ text, final: true, createdAt: new Date().toISOString() }],
      });
      // RTVI send-text: run_immediately defaults to true (acts like barge-in
      // if the bot is mid-speech); reply comes back as speech + transcript.
      await client.sendText(text);
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-full min-h-0 flex-1 flex-col">
        <Thread />
      </div>
    </AssistantRuntimeProvider>
  );
}
