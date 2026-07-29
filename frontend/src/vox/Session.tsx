import { RTVIEvent, type PipecatMetricsData } from "@pipecat-ai/client-js";
import {
  PipecatClientAudio,
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  usePipecatConversation,
  useRTVIClientEvent,
  type BotOutputText,
  type ConversationMessage,
} from "@pipecat-ai/client-react";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

interface SessionProps {
  error?: string | null;
  onConnect?: () => void | Promise<void>;
  onDisconnect?: () => void | Promise<void>;
}

type Phase =
  | "idle"
  | "connecting-mic"
  | "connecting-signal"
  | "connecting-bot"
  | "ready"
  | "user-speaking"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "error"
  | "ended";

type DisplayMode = "karaoke" | "captions" | "instant";
type ReplyMode = "silent" | "spoken";

const DISPLAY_MODES: DisplayMode[] = ["karaoke", "captions", "instant"];

function phaseLabel(phase: Phase): string {
  switch (phase) {
    case "idle":
      return "DISCONNECTED";
    case "connecting-mic":
      return "REQUESTING MICROPHONE";
    case "connecting-signal":
      return "CONNECTING";
    case "connecting-bot":
      return "WAKING BOT";
    case "ready":
      return "LISTENING";
    case "user-speaking":
      return "HEARING YOU";
    case "thinking":
      return "UNDERSTANDING";
    case "speaking":
      return "SPEAKING";
    case "interrupted":
      return "INTERRUPTED";
    case "error":
      return "CONNECTION LOST";
    case "ended":
      return "SESSION ENDED";
    default: {
      const exhaustive: never = phase;
      return exhaustive;
    }
  }
}

function partText(text: unknown): string {
  if (typeof text === "string") return text;
  if (text && typeof text === "object") {
    const value = text as BotOutputText;
    return `${value.spoken ?? ""}${value.unspoken ?? ""}`;
  }
  return "";
}

function messageText(message: ConversationMessage): string {
  return message.parts.map((part) => partText(part.text)).join("");
}

function timeLabel(timestamp: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function pretty(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function AssistantText({
  message,
  mode,
}: {
  message: ConversationMessage;
  mode: DisplayMode;
}) {
  if (mode !== "karaoke") {
    return <>{messageText(message)}</>;
  }

  return (
    <>
      {message.parts.map((part, index) => {
        if (typeof part.text === "string") {
          return <span key={`${part.createdAt}:${index}`}>{part.text}</span>;
        }
        const text = part.text as BotOutputText;
        return (
          <span key={`${part.createdAt}:${index}`}>
            <span>{text.spoken}</span>
            <span className="vx-unspoken">{text.unspoken}</span>
          </span>
        );
      })}
    </>
  );
}

function Orb({ phase, compact = false }: { phase: Phase; compact?: boolean }) {
  const bars = Array.from({ length: 7 }, (_, index) => index);
  const showWaveform = !["idle", "error", "ended"].includes(phase)
    && !phase.startsWith("connecting");
  return (
    <div className={`vx-orb-wrap ${compact ? "vx-orb-compact" : ""} ${showWaveform ? "vx-has-waveform" : ""}`}>
      <div className={`vx-orb vx-orb-${phase}`} />
      {showWaveform && (
        <div className="vx-waveform" aria-hidden="true">
          {bars.map((bar) => (
            <span key={bar} style={{ animationDelay: `${bar * 0.09}s` }} />
          ))}
        </div>
      )}
    </div>
  );
}

function MetricRows({ metrics }: { metrics: PipecatMetricsData | null }) {
  const rows = useMemo(() => {
    if (!metrics) return [];
    return [
      ...(metrics.ttfb ?? []).map((item) => [`${item.processor} TTFB`, item.value]),
      ...(metrics.processing ?? []).map((item) => [item.processor, item.value]),
    ].slice(-6) as [string, number][];
  }, [metrics]);

  if (!rows.length) {
    return <div className="vx-metric-row"><span>No turns yet</span><b>—</b></div>;
  }

  return rows.map(([label, value]) => (
    <div className="vx-metric-row" key={label}>
      <span>{label}</span>
      <b>{value < 10 ? `${value.toFixed(2)} s` : `${Math.round(value)} ms`}</b>
    </div>
  ));
}

export default function Session({ error, onConnect, onDisconnect }: SessionProps) {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();
  const { messages, injectMessage } = usePipecatConversation();
  const [phase, setPhase] = useState<Phase>("idle");
  const [endedByUser, setEndedByUser] = useState(false);
  const [composerText, setComposerText] = useState("");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("captions");
  const [replyMode, setReplyMode] = useState<ReplyMode>("silent");
  const [showSettings, setShowSettings] = useState(false);
  const [showMetrics, setShowMetrics] = useState(false);
  const [metrics, setMetrics] = useState<PipecatMetricsData | null>(null);
  const phaseRef = useRef<Phase>("idle");
  const pendingTextReplyRef = useRef<ReplyMode | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    if (error) setPhase("error");
  }, [error]);

  useEffect(() => {
    if (endedByUser) return;
    switch (transportState) {
      case "disconnected":
        setPhase((current) => current === "error" ? current : "idle");
        break;
      case "initializing":
      case "initialized":
        setPhase("connecting-mic");
        break;
      case "authenticating":
      case "authenticated":
      case "connecting":
        setPhase("connecting-signal");
        break;
      case "connected":
        setPhase("connecting-bot");
        break;
      case "ready":
        setPhase((current) => current.startsWith("connecting") ? "ready" : current);
        break;
      case "disconnecting":
        break;
      case "error":
        setPhase("error");
        break;
      default: {
        const exhaustive: never = transportState;
        return exhaustive;
      }
    }
  }, [endedByUser, transportState]);

  useRTVIClientEvent(RTVIEvent.BotReady, () => setPhase("ready"));
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, () => {
    pendingTextReplyRef.current = null;
    setPhase(phaseRef.current === "speaking" ? "interrupted" : "user-speaking");
  });
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, () => setPhase("thinking"));
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, () => setPhase("thinking"));
  useRTVIClientEvent(RTVIEvent.BotLlmStopped, () => {
    if (pendingTextReplyRef.current === "silent") {
      pendingTextReplyRef.current = null;
      setPhase("ready");
    }
  });
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, () => {
    pendingTextReplyRef.current = null;
    setPhase("speaking");
  });
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, () => setPhase("ready"));
  useRTVIClientEvent(RTVIEvent.Metrics, (data) => setMetrics(data));
  useRTVIClientEvent(RTVIEvent.Error, () => setPhase("error"));

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const hasMessages = messages.length > 0;
  const connected = !["idle", "error", "ended"].includes(phase)
    && !phase.startsWith("connecting");
  const terminal = phase === "error" || phase === "ended";

  async function connect() {
    setEndedByUser(false);
    setPhase("connecting-mic");
    try {
      await onConnect?.();
    } catch {
      setPhase("error");
    }
  }

  async function disconnect() {
    setEndedByUser(true);
    setPhase("ended");
    await onDisconnect?.();
  }

  async function sendText(event?: FormEvent) {
    event?.preventDefault();
    const text = composerText.trim();
    if (!text || !client) return;
    setComposerText("");
    setPhase("thinking");
    pendingTextReplyRef.current = replyMode;
    injectMessage({
      role: "user",
      parts: [{ text, final: true, createdAt: new Date().toISOString() }],
    });
    await client.sendText(text, { audio_response: replyMode === "spoken" });
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      void sendText();
    }
  }

  function openSettings() {
    setShowSettings((open) => !open);
    setShowMetrics(false);
  }

  function openMetrics() {
    setShowMetrics((open) => !open);
    setShowSettings(false);
  }

  return (
    <div className={`vx-root vx-phase-${phase}`}>
      <PipecatClientAudio />
      <div className="vx-brand">VOX</div>
      <div className="vx-toolbar">
        {connected && (
          <>
            <button
              className={`vx-button ${!isMicEnabled ? "vx-button-danger-active" : ""}`}
              onClick={() => enableMic(!isMicEnabled)}
            >
              {isMicEnabled ? "MUTE" : "UNMUTE"}
            </button>
            <button
              className={`vx-button ${showMetrics ? "vx-button-active" : ""}`}
              onClick={openMetrics}
            >
              METRICS
            </button>
          </>
        )}
        <button
          className={`vx-button ${showSettings ? "vx-button-active" : ""}`}
          onClick={openSettings}
        >
          SETTINGS
        </button>
        {connected && (
          <button className="vx-button vx-button-danger" onClick={() => void disconnect()}>
            END
          </button>
        )}
      </div>

      {showSettings && (
        <aside className="vx-popover vx-settings">
          <h2>DISPLAY MODE</h2>
          <div className="vx-segmented">
            {DISPLAY_MODES.map((mode) => (
              <button
                className={displayMode === mode ? "active" : ""}
                key={mode}
                onClick={() => setDisplayMode(mode)}
              >
                {mode.toUpperCase()}
              </button>
            ))}
          </div>
          <p>
            Karaoke tracks spoken progress. Captions show the current response.
            Instant includes text before it is spoken.
          </p>
          <hr />
          <h2>TEXT REPLY MODE</h2>
          <p>Currently: {replyMode === "silent" ? "SILENT REPLIES" : "SPOKEN REPLIES"}.</p>
        </aside>
      )}

      {showMetrics && connected && (
        <aside className="vx-popover vx-metrics">
          <h2>LATENCY (LATEST)</h2>
          <MetricRows metrics={metrics} />
        </aside>
      )}

      {terminal ? (
        <main className="vx-center">
          <Orb phase={phase} />
          <div className="vx-status">{phaseLabel(phase)}</div>
          <p className="vx-terminal-reason">
            {phase === "ended"
              ? "You ended the session. Starting again begins a brand-new conversation."
              : error || "The connection was lost. Check the network and try again."}
          </p>
          <button className="vx-primary" onClick={() => void connect()}>
            Start new session
          </button>
        </main>
      ) : !connected ? (
        <main className="vx-center">
          <Orb phase={phase} />
          <div className="vx-status">{phaseLabel(phase)}</div>
          {phase === "idle" && (
            <>
              <button className="vx-primary" onClick={() => void connect()}>
                Connect
              </button>
              <p className="vx-privacy">
                No history is kept. Closing this tab ends the conversation.
              </p>
            </>
          )}
        </main>
      ) : !hasMessages ? (
        <main className="vx-center">
          <Orb phase={phase} />
          <div className="vx-status">{phaseLabel(phase)}</div>
        </main>
      ) : (
        <main className="vx-transcript-screen">
          <div className="vx-compact-status">
            <Orb phase={phase} compact />
            <div className="vx-status">{phaseLabel(phase)}</div>
          </div>

          <div className="vx-thread" ref={scrollRef}>
            {messages.map((message, index) => {
              const id = `${message.role}:${message.createdAt}:${index}`;
              if (message.role === "function_call" && message.functionCall) {
                const call = message.functionCall;
                const done = call.status === "completed";
                return (
                  <details className="vx-tool-card" key={id}>
                    <summary>
                      <span className={`vx-tool-dot ${done ? "done" : ""}`} />
                      <strong>{call.function_name ?? "tool"}</strong>
                      <span>{done ? "DONE" : "RUNNING…"}</span>
                      <i>⌄</i>
                    </summary>
                    <div className="vx-tool-detail">
                      <label>ARGS</label>
                      <pre>{pretty(call.args ?? {})}</pre>
                      {done && (
                        <>
                          <label>RESULT</label>
                          <pre>{pretty(call.result)}</pre>
                        </>
                      )}
                    </div>
                  </details>
                );
              }

              if (message.role === "system") {
                return <div className="vx-system-turn" key={id}>— {messageText(message)} —</div>;
              }

              if (message.role === "user") {
                return (
                  <article className="vx-turn vx-user-turn" key={id}>
                    <header>YOU · {timeLabel(message.createdAt)}</header>
                    <div>{messageText(message)}</div>
                  </article>
                );
              }

              return (
                <article className="vx-turn vx-assistant-turn" key={id}>
                  <header>
                    VOX · {timeLabel(message.createdAt)} · {replyMode === "silent" ? "TEXT" : "VOICE"}
                  </header>
                  <div>
                    <AssistantText message={message} mode={displayMode} />
                    {message.final === false && <span className="vx-cursor" />}
                  </div>
                </article>
              );
            })}
          </div>

          <form className="vx-composer-wrap" onSubmit={(event) => void sendText(event)}>
            <div className="vx-composer">
              <button
                className="vx-button vx-reply-mode"
                onClick={() => setReplyMode((mode) => mode === "silent" ? "spoken" : "silent")}
                type="button"
              >
                {replyMode === "silent" ? "SILENT REPLIES" : "SPOKEN REPLIES"}
              </button>
              <input
                aria-label="Message Vox"
                onChange={(event) => setComposerText(event.target.value)}
                onKeyDown={onComposerKeyDown}
                placeholder="Type a message — talking works anytime"
                value={composerText}
              />
              <button className="vx-send" disabled={!composerText.trim()} type="submit">
                Send
              </button>
            </div>
          </form>
        </main>
      )}
    </div>
  );
}
