import {
  ClientStatus,
  ConnectButton,
  UserAudioControl,
  VoiceVisualizer,
} from "@pipecat-ai/voice-ui-kit";
import { ConversationThread } from "./ConversationThread";

interface SessionProps {
  error?: string | null;
  onConnect?: () => void | Promise<void>;
  onDisconnect?: () => void | Promise<void>;
}

/**
 * Voice-first composition: the bot's voice artifact is the hero surface,
 * the conversation thread (with text composer) is the supporting panel.
 * Desktop: stage | thread. Mobile: stage collapses to a header strip,
 * thread + composer take the screen.
 */
export default function Session({ error, onConnect, onDisconnect }: SessionProps) {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <header className="flex items-center justify-between border-b border-border px-4 py-2">
        <h1 className="text-sm font-semibold tracking-[0.2em] text-muted-foreground">
          vox
        </h1>
        <div className="flex items-center gap-2">
          <ClientStatus />
          <ConnectButton
            size="sm"
            onConnect={() => onConnect?.()}
            onDisconnect={() => onDisconnect?.()}
          />
        </div>
      </header>

      {error && (
        <div className="border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive-foreground">
          {error}
        </div>
      )}

      <main className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Voice stage — hero on desktop, compact strip on mobile */}
        <section className="flex items-center justify-center gap-6 border-b border-border px-4 py-3 md:w-96 md:flex-col md:border-b-0 md:border-r md:py-0">
          <VoiceVisualizer
            participantType="bot"
            className="size-20 rounded-full bg-card md:size-64"
          />
          <div className="flex items-center gap-3 md:pb-8">
            <UserAudioControl size="lg" />
          </div>
        </section>

        {/* Conversation — assistant-ui registry thread: markdown, action
            bars, composer. Composer submits via RTVI send-text. */}
        <section className="flex min-h-0 flex-1 flex-col">
          <ConversationThread />
        </section>
      </main>
    </div>
  );
}
