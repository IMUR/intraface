// UI wiring: connection state machine, transcript, thinking indicator, meter.

import { VoxConnection } from "./signaling.js";
import { Transcript } from "./transcript.js";
import { Meter } from "./meter.js";

const $ = (id) => document.getElementById(id);

const statusEl = $("status");
const statusText = $("status-text");
const connectBtn = $("connect");
const clearBtn = $("clear");
const thinkingEl = $("thinking");
const remoteAudio = $("remote");
const meterFill = $("meter-fill");

const transcript = new Transcript($("transcript"));
const meter = new Meter((level) => {
  meterFill.style.width = `${Math.round(level * 100)}%`;
});

// Human-readable labels for raw connection states.
const STATE_LABELS = {
  idle: "idle",
  "requesting-mic": "mic…",
  signaling: "signaling…",
  new: "connecting…",
  connecting: "connecting…",
  connected: "live",
  disconnected: "lost",
  failed: "failed",
  closed: "idle",
};

let conn = null;

function setThinking(on) {
  thinkingEl.hidden = !on;
}

// MUST (§3.6): the connect control is re-enabled on "connected" — this was
// a bring-up bug. Button becomes "disconnect" while live.
function onState(state) {
  statusEl.dataset.state = state;
  statusText.textContent = STATE_LABELS[state] ?? state;

  if (state === "connected") {
    connectBtn.disabled = false;
    connectBtn.textContent = "disconnect";
    connectBtn.dataset.mode = "disconnect";
  } else if (state === "disconnected" || state === "failed" || state === "closed") {
    // Backend has no persistence; a dropped connection ends the session (§6).
    teardown();
  } else {
    connectBtn.disabled = true;
    connectBtn.textContent = "connect";
    delete connectBtn.dataset.mode;
  }
}

// Turn-atomic messages (§4). A user turn arriving means the bot is now in
// the ~2–3 s LLM+TTS window (§6) — show the thinking state until the
// assistant turn lands.
function onMessage({ role, text }) {
  transcript.add(role, text);
  setThinking(role === "user");
}

function teardown() {
  meter.stop();
  remoteAudio.srcObject = null;
  setThinking(false);
  conn = null;
  connectBtn.disabled = false;
  connectBtn.textContent = "connect";
  delete connectBtn.dataset.mode;
}

connectBtn.addEventListener("click", async () => {
  if (conn) {
    conn.disconnect();
    return; // "closed" state flows through onState → teardown()
  }
  conn = new VoxConnection({
    onState,
    onMessage,
    onRemoteStream: (stream) => { remoteAudio.srcObject = stream; },
    onMicStream: (stream) => meter.start(stream),
  });
  connectBtn.disabled = true;
  try {
    await conn.connect();
  } catch (err) {
    console.error("vox: connect failed", err);
    statusEl.dataset.state = "failed";
    statusText.textContent = err?.name === "NotAllowedError" ? "mic denied" : "failed";
    conn?.disconnect();
  }
});

clearBtn.addEventListener("click", () => transcript.clear());
