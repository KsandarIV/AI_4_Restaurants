// Gira nel thread audio: porta il microfono a PCM16 mono 16 kHz in frame fissi.
class MicProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = options.processorOptions;
    this.ratio = sampleRate / o.targetRate;       // sampleRate = frequenza del contesto audio
    this.frameSize = Math.round(o.targetRate * o.frameMs / 1000);
    this.pos = 0;                                 // quanti campioni in ingresso mancano al prossimo campione d'uscita
    this.sum = 0; this.count = 0;                 // media dei campioni che finiscono in un campione d'uscita
    this.out = new Int16Array(this.frameSize);
    this.n = 0;
  }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.sum += ch[i]; this.count++;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const v = Math.max(-1, Math.min(1, this.sum / this.count));
        this.out[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        this.sum = 0; this.count = 0;
        if (this.n === this.frameSize) {
          this.port.postMessage(this.out.buffer.slice(0));
          this.n = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("mic-processor", MicProcessor);
