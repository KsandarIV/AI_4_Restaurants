// Interfaccia dell'assistente: finestra, schede "Scrivi"/"Parla", log dei messaggi.
(function () {
  const $ = (id) => document.getElementById(id);
  const panel = $("assistant"), fab = $("assistant-fab");
  const log = $("chat-log"), form = $("chat-form"), input = $("chat-input");
  const voiceBtn = $("voice-toggle"), voiceLabel = $("voice-label"), voiceState = $("voice-state");
  let started = false, busy = false;

  // Il modello risponde in Markdown: lo converto in nodi DOM (mai innerHTML, il testo resta sicuro).
  function inline(parent, text) {
    text.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        const s = document.createElement("strong");
        s.textContent = part.slice(2, -2);
        parent.append(s);
      } else if (part) {
        parent.append(part.replace(/\*+/g, ""));
      }
    });
  }

  function renderMarkdown(box, text) {
    let list = null;
    text.split("\n").forEach((raw) => {
      const line = raw.trim();
      const bullet = line.match(/^[*\-•]\s+(.*)/);
      if (bullet) {
        if (!list) { list = document.createElement("ul"); box.append(list); }
        const li = document.createElement("li");
        inline(li, bullet[1]);
        list.append(li);
        return;
      }
      list = null;
      if (!line) return;
      const p = document.createElement("p");
      inline(p, line.replace(/^#+\s*/, ""));
      box.append(p);
    });
  }

  function addMessage(kind, text) {
    const m = document.createElement("div");
    m.className = "msg " + kind;
    if (kind === "bot") renderMarkdown(m, text);
    else m.textContent = text;
    log.append(m);
    log.scrollTop = log.scrollHeight;
    return m;
  }

  async function startChat() {
    log.replaceChildren();
    busy = false;
    try {
      addMessage("bot", await ChatClient.start());
      started = true;
    } catch (e) {
      started = false;
      addMessage("error", e.message);
    }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    if (!started) await startChat();
    if (!started) return;
    input.value = "";
    addMessage("user", text);
    const wait = addMessage("bot typing", "Sto scrivendo…");
    busy = true;
    try {
      const reply = await ChatClient.send(text);
      wait.remove();
      addMessage("bot", reply);
    } catch (e) {
      wait.remove();
      addMessage("error", e.message);
    }
    busy = false;
    input.focus();
  });

  $("chat-reset").addEventListener("click", startChat);

  // ---------- schede ----------
  function setMode(mode) {
    const voice = mode === "voice";
    $("pane-chat").hidden = voice;
    $("pane-voice").hidden = !voice;
    $("tab-chat").setAttribute("aria-selected", String(!voice));
    $("tab-voice").setAttribute("aria-selected", String(voice));
    if (!voice) { VoiceClient.stop(); input.focus(); }
  }
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));

  async function refreshStatus() {
    const s = $("assistant-status");
    const ok = await window.checkBackend();
    s.textContent = ok ? "Online" : "Server non raggiungibile";
    s.className = ok ? "ok" : "ko";
  }

  function openAssistant(mode) {
    mode = mode || "chat";
    panel.hidden = false;
    fab.hidden = true;
    setMode(mode);
    refreshStatus();
    if (!started && mode === "chat") startChat();
  }
  function closeAssistant() {
    VoiceClient.stop();
    panel.hidden = true;
    fab.hidden = false;
  }
  document.querySelectorAll("[data-open-assistant]").forEach((b) =>
    b.addEventListener("click", () => openAssistant(b.dataset.mode)));
  $("assistant-close").addEventListener("click", closeAssistant);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) closeAssistant(); });

  // ---------- voce ----------
  const LABELS = {
    off: ["Tocca per parlare", "Spento"],
    connecting: ["Mi collego…", "Connessione in corso"],
    listening: ["Ti ascolto", "Parla pure"],
    speaking: ["Sto parlando", "Puoi interrompermi"],
  };
  function showVoiceState(state) {
    const [label, text] = LABELS[state] || LABELS.off;
    voiceLabel.textContent = label;
    voiceState.textContent = text;
    voiceBtn.setAttribute("aria-pressed", String(state !== "off"));
    voiceBtn.dataset.state = state;
  }
  voiceBtn.addEventListener("click", async () => {
    if (VoiceClient.active) { VoiceClient.stop(); return; }
    try {
      await VoiceClient.start(showVoiceState);
    } catch (e) {
      VoiceClient.stop();
      voiceState.textContent = e.message;
    }
  });
  window.addEventListener("beforeunload", () => VoiceClient.stop());
})();
