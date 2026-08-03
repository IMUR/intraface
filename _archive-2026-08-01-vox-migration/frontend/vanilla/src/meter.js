// Mic input level meter via AnalyserNode.
// Analysis-only tap on the already-acquired getUserMedia stream — AEC stays
// in the capture path and is not bypassed (surface doc §5).

export class Meter {
  /** @param {function} onLevel (level: number 0..1) */
  constructor(onLevel) {
    this.onLevel = onLevel;
    this.ctx = null;
    this.raf = null;
  }

  /** @param {MediaStream} stream */
  start(stream) {
    this.stop();
    this.ctx = new AudioContext();
    const src = this.ctx.createMediaStreamSource(stream);
    const analyser = this.ctx.createAnalyser();
    analyser.fftSize = 512;
    src.connect(analyser);

    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) {
        const d = (v - 128) / 128;
        sum += d * d;
      }
      // RMS, scaled up so normal speech fills a useful range.
      this.onLevel(Math.min(1, Math.sqrt(sum / buf.length) * 3.5));
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = null;
    this.ctx?.close();
    this.ctx = null;
    this.onLevel(0);
  }
}
