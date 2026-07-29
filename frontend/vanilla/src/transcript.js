// Turn-atomic transcript store with localStorage persistence.
// The backend delivers one message per completed turn (surface doc §4) —
// there is no partial/streaming transcript data to handle.

const STORAGE_KEY = "vox.transcript.v1";

export class Transcript {
  /** @param {HTMLElement} container */
  constructor(container) {
    this.el = container;
    this.turns = this._load();
    for (const turn of this.turns) this._appendEl(turn);
    this._scrollToEnd();
  }

  /** @param {"user"|"assistant"} role @param {string} text */
  add(role, text) {
    const turn = { role, text, t: Date.now() };
    this.turns.push(turn);
    this._appendEl(turn);
    this._save();
    this._scrollToEnd();
  }

  clear() {
    this.turns = [];
    this._save();
    this.el.replaceChildren();
  }

  _appendEl({ role, text }) {
    const div = document.createElement("div");
    div.className = `turn ${role}`;
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "user" ? "you" : "core";
    div.append(who, document.createTextNode(text));
    this.el.append(div);
  }

  _scrollToEnd() {
    this.el.scrollTop = this.el.scrollHeight;
  }

  _load() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? [];
    } catch {
      return [];
    }
  }

  _save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.turns));
    } catch {
      // Quota or privacy mode — persistence is best-effort.
    }
  }
}
