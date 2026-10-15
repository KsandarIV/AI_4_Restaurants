// Client del VOICE (WebSocket /ws/voice): microfono -> PCM16 16 kHz -> server; server -> PCM16 -> altoparlanti.
// Protocollo (vedi voice/README_VOICE.md): binari = audio; testo JSON = {"event": "ready"|"barge_in"}.
window.VoiceClient = (function () {
  const cfg = window.CONFIG.voice;
  let ws = null, ctx = null, stream = null, node = null, source = null, mute = null;
  let outRate = cfg.outputSampleRate;
  let playHead = 0;
  let playing = [];
  let onState = () => {};

  function stopPlayback() {
    playing.forEach((s) => { try { s.stop(); } catch (e) { /* già finito */ } });
    playing = [];
    playHead = 0;
  }

  function play(arrayBuffer) {
    if (!ctx) return;
    const pcm = new Int16Array(arrayBuffer, 0, Math.floor(arrayBuffer.byteLength / 2));
    if (!pcm.length) return;
    const buf = ctx.createBuffer(1, pcm.length, outRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) data[i] = pcm[i] / 32768;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    playHead = Math.max(playHead, ctx.currentTime + 0.05);
    src.start(playHead);
    playHead += buf.duration;
    playing.push(src);
    onState("speaking");
    src.onended = () => {
      playing = playing.filter((s) => s !== src);
      if (!playing.length && ws) onState("listening");
    };
  }

  async function start(stateCallback) {
    onState = stateCallback || onState;
    if (!navigator.mediaDevices || !window.isSecureContext) {
      throw new Error("Il microfono richiede una pagina sicura: apri il sito da http://localhost:8080 oppure con HTTPS.");
    }
    onState("connecting");
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) {
      throw new Error("Permesso al microfono negato.");
    }
    ctx = new AudioContext();
    await ctx.audioWorklet.addModule("js/mic-worklet.js");
    source = ctx.createMediaStreamSource(stream);
    node = new AudioWorkletNode(ctx, "mic-processor", {
      processorOptions: { targetRate: cfg.inputSampleRate, frameMs: cfg.frameMs },
    });
    mute = ctx.createGain();   // il nodo deve essere collegato per funzionare, ma non vogliamo risentirci
    mute.gain.value = 0;
    source.connect(node).connect(mute).connect(ctx.destination);

    await new Promise((resolve, reject) => {
      ws = new WebSocket(cfg.wsUrl);
      ws.binaryType = "arraybuffer";
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error("Non riesco a contattare il servizio vocale. Controlla che sia acceso."));
    });
    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        let m;
        try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (m.event === "ready" && m.tts_sample_rate) outRate = m.tts_sample_rate;
        if (m.event === "barge_in") { stopPlayback(); onState("listening"); }
      } else {
        play(ev.data);
      }
    };
    ws.onclose = () => { if (ws) stop(); };
    node.port.onmessage = (ev) => { if (ws && ws.readyState === 1) ws.send(ev.data); };
    onState("listening");
  }

  function stop() {
    const w = ws;
    ws = null;
    if (w) { try { w.close(); } catch (e) { /* già chiuso */ } }
    stopPlayback();
    if (node) { node.port.onmessage = null; node.disconnect(); node = null; }
    if (source) { source.disconnect(); source = null; }
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    if (ctx) { ctx.close(); ctx = null; }
    onState("off");
  }

  return { start, stop, get active() { return !!ws; } };
})();
