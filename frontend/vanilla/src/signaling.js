// WebRTC + signaling for the vox backend.
// Implements every MUST from docs/vox-frontend-surface.md §2–§3.
// Surface-doc references appear inline as (§n).

const DEFAULT_ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }]; // STUN only, no TURN (§3.4)

export class VoxConnection {
  /**
   * @param {object}   opts
   * @param {string}   opts.apiBase        Origin prefix for /api routes ("" = same origin).
   * @param {function} opts.onState        (state: string) — raw pc.connectionState plus
   *                                       "requesting-mic" | "signaling" | "closed".
   * @param {function} opts.onMessage      (msg: {role, text}) — data channel messages (§4).
   * @param {function} opts.onRemoteStream (stream: MediaStream) — bot audio (§3.5).
   * @param {function} opts.onMicStream    (stream: MediaStream) — local mic, for metering.
   */
  constructor({ apiBase = "", onState = () => {}, onMessage = () => {},
                onRemoteStream = () => {}, onMicStream = () => {} } = {}) {
    this.apiBase = apiBase;
    this.onState = onState;
    this.onMessage = onMessage;
    this.onRemoteStream = onRemoteStream;
    this.onMicStream = onMicStream;
    this.pc = null;
    this.dc = null;
    this.pcId = null;
    this.micStream = null;
    this._pendingIce = [];
  }

  get connected() {
    return this.pc?.connectionState === "connected";
  }

  async connect() {
    if (this.pc) return;

    this._setState("requesting-mic");
    // Always-listening mic; endpointing is server-side (VAD + Smart Turn) (§5).
    // Standard getUserMedia keeps browser AEC in the path — do not bypass (§5).
    this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.onMicStream(this.micStream);

    const pc = new RTCPeerConnection({ iceServers: DEFAULT_ICE_SERVERS });
    this.pc = pc;

    // MUST (§3.1): the client creates data channel "pipecat" BEFORE the offer.
    // Pipecat listens server-side via on("datachannel"); reordering this drops
    // transcripts silently and the server times out after 10 s.
    this.dc = pc.createDataChannel("pipecat");
    this.dc.onmessage = (ev) => {
      try {
        this.onMessage(JSON.parse(ev.data));
      } catch {
        console.warn("vox: ignoring non-JSON data channel message", ev.data);
      }
    };

    // MUST (§3.2): both audio and video m-lines, sendrecv. Video is unused but
    // required by SmallWebRTCTransport. addTrack(audio) yields sendrecv audio.
    for (const track of this.micStream.getAudioTracks()) {
      pc.addTrack(track, this.micStream);
    }
    pc.addTransceiver("video", { direction: "sendrecv" });

    // MUST (§3.5): play remote bot audio.
    pc.ontrack = (ev) => {
      if (ev.track.kind === "audio") this.onRemoteStream(ev.streams[0]);
    };

    // MUST (§3.3): candidates gathered before pc_id is known must be queued.
    pc.onicecandidate = (ev) => {
      if (ev.candidate) this._sendOrQueueIce(ev.candidate);
    };

    // MUST (§3.6): full state machine — the UI re-enables on "connected".
    pc.onconnectionstatechange = () => this._setState(pc.connectionState);

    this._setState("signaling");
    await pc.setLocalDescription(await pc.createOffer());

    // POST /api/offer (§2)
    const res = await fetch(`${this.apiBase}/api/offer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, type: "offer" }),
    });
    if (!res.ok) throw new Error(`POST /api/offer failed: ${res.status}`);
    const answer = await res.json();
    this.pcId = answer.pc_id;
    await pc.setRemoteDescription(answer);

    // MUST (§3.3): flush the queue now that pc_id exists.
    for (const c of this._pendingIce) await this._sendIce(c);
    this._pendingIce = [];
  }

  disconnect() {
    this.dc?.close();
    this.pc?.close();
    this.pc = null;
    this.dc = null;
    this.pcId = null;
    this._pendingIce = [];
    this.micStream?.getTracks().forEach((t) => t.stop());
    this.micStream = null;
    this._setState("closed");
  }

  async _sendOrQueueIce(candidate) {
    if (this.pcId) await this._sendIce(candidate);
    else this._pendingIce.push(candidate);
  }

  // PATCH /api/offer — trickle ICE (§2)
  async _sendIce(candidate) {
    const res = await fetch(`${this.apiBase}/api/offer`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pc_id: this.pcId,
        candidates: [{
          candidate: candidate.candidate,
          sdp_mid: candidate.sdpMid,
          sdp_mline_index: candidate.sdpMLineIndex,
        }],
      }),
    });
    if (!res.ok) console.warn("vox: ICE PATCH failed", res.status);
  }

  _setState(state) {
    this.state = state;
    this.onState(state);
  }
}
