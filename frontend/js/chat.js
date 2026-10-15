// Client del servizio CHAT (chat/api.py). Non conosce né il BE né l'LLM.
window.ChatClient = (function () {
  const { baseUrl, sessionPath, messagePath, timeoutMs } = window.CONFIG.chat;
  let sessionId = null;

  async function post(path, body) {
    let r;
    try {
      r = await fetch(baseUrl + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (e) {
      throw new Error(e.name === "TimeoutError"
        ? "Il server ci sta mettendo troppo a rispondere. Riprova tra poco."
        : "Non riesco a contattare il servizio chat. Controlla che sia acceso.");
    }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || "Errore del servizio chat (" + r.status + ").");
    return data;
  }

  return {
    /** Avvia una nuova conversazione. Restituisce il messaggio iniziale del bot. */
    async start() {
      const d = await post(sessionPath);
      sessionId = d.session_id;
      return d.reply;
    },
    /** Invia un messaggio. Restituisce il testo del bot. Se la sessione è scaduta la prossima volta ne riparte una. */
    async send(text) {
      if (!sessionId) await this.start();
      try {
        return (await post(messagePath, { session_id: sessionId, text })).reply;
      } catch (e) {
        if (/scaduta/i.test(e.message)) sessionId = null;
        throw e;
      }
    },
  };
})();
