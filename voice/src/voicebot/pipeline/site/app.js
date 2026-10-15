// Trattoria Bella Napoli - voice site.
// Same kind of site as the chat bot's (menu, hours, assistant) plus "My reservations".
// Menu / info / reservation lookups go through THIS server (/site/*), never straight to the BE.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  // ---------------------------------------------------------------- texts
  const T = {
    it: {
      nav_about: "Chi siamo", nav_menu: "Menu", nav_reservations: "Le mie prenotazioni", nav_where: "Dove siamo",
      book_by_voice: "Prenota a voce", check_reservations: "Controlla le mie prenotazioni",
      eyebrow: "Trattoria · Via Toledo, Napoli",
      hero_title: "La cucina campana, come a casa della nonna.",
      hero_lead: "Paste di Gragnano, pomodori San Marzano, mozzarella di bufala. Prenota il tuo tavolo parlando con il nostro assistente.",
      about_text: "Dal 1987 serviamo i piatti della tradizione napoletana con materie prime del territorio. Tre ambienti: la sala interna, la terrazza e il giardino estivo. Ogni tavolo è libero per un turno di 90 minuti.",
      f1_title: "3 ambienti", f1_text: "sala, terrazza, giardino",
      f2_title: "Senza glutine", f2_text: "e opzioni vegetariane e vegane",
      f3_title: "Per tutti", f3_text: "accesso disabili, seggioloni, animali ammessi",
      menu_loading: "Carico il menu…", menu_unavailable: "Il menu non è al momento disponibile. Riprova tra poco o chiedi all'assistente.",
      menu_note: "Le allergie e le intolleranze vanno segnalate al momento della prenotazione. I prezzi sono in euro.",
      all: "Tutti", vegan: "vegano", vegetarian: "vegetariano", gluten_free: "senza glutine", allergens: "allergeni",
      res_intro: "Dopo ogni prenotazione a voce la trovi qui, con lo stato aggiornato. Per controllarne una usa il codice (RES-…): funziona solo da questo browser, dopo esserti registrato parlando con l'assistente.",
      lookup_placeholder: "Codice prenotazione, es. RES-9A8B2C", lookup_button: "Controlla", refresh_all: "Aggiorna tutte",
      no_reservations: "Nessuna prenotazione in questo browser.",
      need_registration: "Per controllare una prenotazione devi prima registrarti parlando con l'assistente (da questo browser).",
      not_found: "Prenotazione non trovata (controlla il codice: la vedi solo se è tua).",
      server_error: "Non riesco a controllare adesso: riprova tra poco.",
      status_confirmed: "Confermata", status_cancelled: "Cancellata", status_unknown: "Sconosciuta",
      persons: "persone", person: "persona", table: "tavolo", refresh: "Aggiorna", remove: "Rimuovi",
      h_address: "Indirizzo", h_hours: "Orari", h_parking: "Parcheggio", h_phone: "Telefono", h_services: "Servizi", h_payments: "Pagamenti",
      assistant_title: "Assistente vocale", close: "Chiudi", orb_aria: "Tocca per avviare o terminare la conversazione",
      new_conversation: "Nuova conversazione", hang_up: "Termina",
      toast_confirmed: "Prenotazione confermata", toast_updated: "Prenotazione aggiornata",
      toast_guests: "{n} persone", toast_guest_one: "1 persona",
      st_off: "Tocca il cerchio per parlare", st_connecting: "Mi collego…", st_loading: "Carico i modelli vocali…",
      st_listening: "Ti ascolto… fai una pausa quando hai finito", st_heard: "Ok…", st_thinking: "Ci penso…",
      st_speaking: "Parlo… puoi interrompermi", st_retry: "Connessione persa: riprovo tra {s} s…",
      st_ended: "Conversazione terminata", st_error: "Problema: {d}",
      ok_online: "in linea", ko_offline: "server non raggiungibile",
      insecure: "Il microfono richiede una pagina sicura: apri http://localhost:{p}/ su questo PC, oppure da un altro PC usa: python -m voicebot live ws://{h}/ws/voice",
      you: "Tu", bot: "Assistente",
      banner_local: "TEST LOCALE — BE finto: nessun dato reale viene toccato",
    },
    en: {
      nav_about: "About", nav_menu: "Menu", nav_reservations: "My reservations", nav_where: "Find us",
      book_by_voice: "Book by voice", check_reservations: "Check my reservations",
      eyebrow: "Trattoria · Via Toledo, Naples",
      hero_title: "Campanian cooking, just like grandma's.",
      hero_lead: "Gragnano pasta, San Marzano tomatoes, buffalo mozzarella. Book your table by talking to our assistant.",
      about_text: "Since 1987 we serve the dishes of the Neapolitan tradition with local ingredients. Three rooms: indoors, the terrace and the summer garden. Each table is yours for a 90-minute turn.",
      f1_title: "3 rooms", f1_text: "indoor, terrace, garden",
      f2_title: "Gluten free", f2_text: "and vegetarian and vegan options",
      f3_title: "For everyone", f3_text: "wheelchair access, high chairs, pets welcome",
      menu_loading: "Loading the menu…", menu_unavailable: "The menu is not available right now. Try again shortly or ask the assistant.",
      menu_note: "Please tell us about allergies and intolerances when booking. Prices are in euro.",
      all: "All", vegan: "vegan", vegetarian: "vegetarian", gluten_free: "gluten free", allergens: "allergens",
      res_intro: "After each booking by voice you find it here, with its up-to-date status. To check one use its code (RES-…): it works only from this browser, after you registered by talking to the assistant.",
      lookup_placeholder: "Booking code, e.g. RES-9A8B2C", lookup_button: "Check", refresh_all: "Refresh all",
      no_reservations: "No reservations in this browser.",
      need_registration: "To check a reservation you first need to register by talking to the assistant (from this browser).",
      not_found: "Reservation not found (check the code: you can only see your own).",
      server_error: "I cannot check right now: try again shortly.",
      status_confirmed: "Confirmed", status_cancelled: "Cancelled", status_unknown: "Unknown",
      persons: "people", person: "person", table: "table", refresh: "Refresh", remove: "Remove",
      h_address: "Address", h_hours: "Opening hours", h_parking: "Parking", h_phone: "Phone", h_services: "Services", h_payments: "Payments",
      assistant_title: "Voice assistant", close: "Close", orb_aria: "Tap to start or end the conversation",
      new_conversation: "New conversation", hang_up: "Hang up",
      toast_confirmed: "Booking confirmed", toast_updated: "Booking updated",
      toast_guests: "{n} guests", toast_guest_one: "1 guest",
      st_off: "Tap the circle to talk", st_connecting: "Connecting…", st_loading: "Loading the speech models…",
      st_listening: "Listening… pause when you are done", st_heard: "Got it…", st_thinking: "Thinking…",
      st_speaking: "Speaking… you can interrupt", st_retry: "Connection lost: retrying in {s} s…",
      st_ended: "Conversation ended", st_error: "Problem: {d}",
      ok_online: "online", ko_offline: "server unreachable",
      insecure: "The microphone needs a secure page: open http://localhost:{p}/ on this PC, or from another PC run: python -m voicebot live ws://{h}/ws/voice",
      you: "You", bot: "Assistant",
      banner_local: "LOCAL TEST — stub BE: no real data is touched",
    },
  };
  let LANG = "it";
  const t = (key, vars) => {
    let s = (T[LANG] && T[LANG][key]) || T.it[key] || key;
    Object.entries(vars || {}).forEach(([k, v]) => { s = s.replace("{" + k + "}", v); });
    return s;
  };
  function applyI18n() {
    document.documentElement.lang = LANG;
    document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((n) => { n.placeholder = t(n.dataset.i18nPlaceholder); });
    document.querySelectorAll("[data-i18n-aria]").forEach((n) => { n.setAttribute("aria-label", t(n.dataset.i18nAria)); });
  }

  async function getJson(path, opts) {
    const r = await fetch(path, { signal: AbortSignal.timeout(10000), ...(opts || {}) });
    if (!r.ok) { const e = new Error("HTTP " + r.status); e.status = r.status; throw e; }
    return r.json();
  }

  // ---------------------------------------------------------------- menu + info (via this server)
  let dishes = [], activeCategory = null;

  function tags(d) {
    const out = [];
    if (d.is_vegan) out.push(t("vegan")); else if (d.is_vegetarian) out.push(t("vegetarian"));
    if (d.is_gluten_free) out.push(t("gluten_free"));
    if (d.allergens) out.push(t("allergens") + ": " + d.allergens);
    return out.join(" · ");
  }
  function renderMenu() {
    const box = $("menu-list");
    box.replaceChildren();
    const cats = [...new Set(dishes.map((d) => d.category))];
    cats.filter((c) => !activeCategory || c === activeCategory).forEach((cat) => {
      box.append(el("h3", "cat", cat));
      dishes.filter((d) => d.category === cat).forEach((d) => {
        const row = el("div", "dish"), left = el("div");
        left.append(el("div", "dish-name", d.name));
        if (d.description) left.append(el("div", "dish-desc", d.description));
        if (tags(d)) left.append(el("div", "dish-tags", tags(d)));
        row.append(left, el("div", "dish-price", "€ " + Number(d.price).toFixed(2).replace(".", ",")));
        box.append(row);
      });
    });
  }
  function renderFilters() {
    const box = $("menu-filters");
    box.replaceChildren();
    [null, ...new Set(dishes.map((d) => d.category))].forEach((c) => {
      const b = el("button", "chip", c || t("all"));
      b.type = "button";
      b.setAttribute("aria-pressed", String(c === activeCategory));
      b.onclick = () => { activeCategory = c; renderFilters(); renderMenu(); };
      box.append(b);
    });
  }
  async function loadMenu() {
    try {
      dishes = await getJson("/site/menu");
      if (!dishes.length) throw new Error("empty");
      renderFilters(); renderMenu();
    } catch (e) {
      $("menu-list").textContent = t("menu_unavailable");
    }
  }
  async function loadInfo() {
    try {
      const info = await getJson("/site/info");
      document.querySelectorAll("[data-info]").forEach((n) => {
        const v = info[n.dataset.info];
        if (!v) return;
        n.textContent = v;
        if (n.dataset.link === "tel") n.href = "tel:" + String(v).replace(/[^\d+]/g, "");
      });
    } catch (e) { /* the page keeps its placeholders */ }
  }

  // ---------------------------------------------------------------- my reservations
  const STORE = "bella-napoli-voice";
  function load() {
    try { return { customer_id: "", items: [], ...JSON.parse(localStorage.getItem(STORE) || "{}") }; }
    catch (e) { return { customer_id: "", items: [] }; }
  }
  function save(state) { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) { /* private mode */ } }
  let store = load();

  function upsert(res) {
    const i = store.items.findIndex((x) => x.code === res.code);
    const merged = { ...(i >= 0 ? store.items[i] : {}), ...res, updated: Date.now() };
    if (i >= 0) store.items[i] = merged; else store.items.unshift(merged);
    save(store); renderReservations();
  }
  function statusBadge(status) {
    const s = String(status || "").toUpperCase();
    const kind = s === "CONFIRMED" ? "confirmed" : s === "CANCELLED" ? "cancelled" : "unknown";
    return el("span", "badge " + kind, t("status_" + kind));
  }
  function renderReservations() {
    const box = $("res-list");
    box.replaceChildren();
    if (!store.items.length) { box.append(el("p", "empty", t("no_reservations"))); return; }
    store.items.forEach((r) => {
      const card = el("div", "res-card"), main = el("div", "res-main");
      main.append(el("span", "res-code", r.code));
      const n = Number(r.guests) || 0;
      const parts = [r.date, r.time, n ? n + " " + (n === 1 ? t("person") : t("persons")) : "",
                     r.table ? t("table") + " " + r.table + (r.location ? " (" + r.location + ")" : "") : ""];
      main.append(el("span", "res-meta", parts.filter(Boolean).join(" · ")));
      const actions = el("div", "res-actions");
      const refresh = el("button", "btn btn-small btn-outline", t("refresh"));
      refresh.type = "button"; refresh.onclick = () => refreshOne(r.code, true);
      const remove = el("button", "link-btn", t("remove"));
      remove.type = "button";
      remove.onclick = () => { store.items = store.items.filter((x) => x.code !== r.code); save(store); renderReservations(); };
      actions.append(refresh, remove);
      card.append(main, statusBadge(r.status), actions);
      box.append(card);
    });
  }
  // Ask the BE (through this server) how a booking stands now. Returns "ok" | "none" | "notfound" | "error".
  async function refreshOne(code, loud) {
    const msg = $("lookup-msg");
    if (!store.customer_id) { if (loud) msg.textContent = t("need_registration"); return "none"; }
    try {
      const d = await getJson("/site/reservation/" + encodeURIComponent(code) + "?customer_id=" + encodeURIComponent(store.customer_id));
      upsert({ code: d.booking_code || code, date: d.date, time: d.time, guests: d.guests_count, status: d.status,
               table: d.table_number, location: d.table_location });
      if (loud) msg.textContent = "";
      return "ok";
    } catch (e) {
      if (loud) msg.textContent = e.status === 404 ? t("not_found") : t("server_error");
      return e.status === 404 ? "notfound" : "error";
    }
  }
  async function refreshAll() { for (const r of [...store.items]) await refreshOne(r.code, false); }

  $("lookup").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const code = $("lookup-code").value.trim().toUpperCase();
    if (code) refreshOne(code, true);
  });
  $("refresh-all").addEventListener("click", () => { $("lookup-msg").textContent = ""; refreshAll(); });

  // ---------------------------------------------------------------- assistant (voice)
  const SR = 16000;
  let ws = null, ctx = null, stream = null, proc = null, curSrc = null;
  let wantLive = false, live = false, retry = 0, retryTimer = null;
  let playQ = [], playing = false, ttsRate = 22050, level = 0, mode = "idle", ripples = [];
  const orb = $("orb"), g = orb.getContext("2d");

  function setState(key, vars) { $("state").textContent = t(key, vars); }
  function logLine(who, text) {
    const m = el("div", "msg " + who, text);
    $("chat-log").append(m);
    m.scrollIntoView({ block: "nearest" });
  }
  function setAssistantStatus(ok) {
    const s = $("assistant-status");
    s.className = ok ? "ok" : "ko";
    s.textContent = ok ? t("ok_online") : t("ko_offline");
  }
  async function checkServer() {
    try { await getJson("/health"); setAssistantStatus(true); } catch (e) { setAssistantStatus(false); }
  }
  function openAssistant() {
    $("assistant").hidden = false;
    $("assistant-fab").hidden = true;
    checkServer();
    if (!window.isSecureContext) {
      const w = $("insecure");
      w.hidden = false;
      w.textContent = t("insecure", { p: location.port || "8003", h: location.host });
    }
    if (!wantLive) setState("st_off");
  }
  function closeAssistant() {
    hangUp();
    $("assistant").hidden = true;
    $("assistant-fab").hidden = false;
  }
  document.querySelectorAll("[data-open-assistant]").forEach((b) => b.addEventListener("click", openAssistant));
  $("assistant-close").addEventListener("click", closeAssistant);
  $("hangup").addEventListener("click", hangUp);
  $("reset").addEventListener("click", () => {
    $("chat-log").replaceChildren();
    stopPlayback();
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ cmd: "reset" }));
  });

  // liquid orb, same animation as the test page (blob + orbiting dots + ripples + flashes)
  let flash = 0, flashRed = 0;
  // ---- orb liquido: blob seno/coseno + puntini orbitali ----
  const CX = 260, CY = 260, R = 150;
  const dots = Array.from({ length: 16 }, (_, i) => {
    const base = R * (0.78 + Math.random() * 0.34);
    return {
      a: (i / 16) * Math.PI * 2, r: base, base,
      s: 3.5 + Math.random() * 2.5, o: 0.5 + Math.random() * 0.4
    };
  });
  function wave(theta, t, amp) {
    return amp * (Math.sin(3 * theta + t * 1.7) * 0.55
                + Math.cos(5 * theta - t * 2.3) * 0.30
                + Math.sin(8 * theta + t * 3.1) * 0.15);
  }
  function draw(tms) {
    const t = tms / 1000;
    g.clearRect(0, 0, 520, 520);
    const active = live ? 1 : 0;
    // velocita' puntini per stato: spento = lenti, ascolto = medi, pensiero = veloci
    const spin = mode === "thinking" ? 2.6 : 0.15 + active * 1.6 + (mode === "speaking" ? 1.2 : 0);
    const amp = mode === "heard" ? 7 : 5 + level * 34 + (mode === "speaking" ? 10 : 0);
    const rot = mode === "thinking" ? t * 0.6 : 0;  // il pensiero "ruota" piano
    // blob
    const grad = g.createRadialGradient(CX - 40, CY - 50, 20, CX, CY, R + 40);
    grad.addColorStop(0, "#d95f43"); grad.addColorStop(0.6, "#b3341f"); grad.addColorStop(1, "#8a2615");
    g.beginPath();
    for (let i = 0; i <= 120; i++) {
      const th = (i / 120) * Math.PI * 2 + rot;
      const rr = R + wave(th, t, amp);
      const x = CX + rr * Math.cos(th), y = CY + rr * Math.sin(th);
      i ? g.lineTo(x, y) : g.moveTo(x, y);
    }
    g.closePath();
    g.fillStyle = grad;
    g.shadowColor = "rgba(179,52,31,.55)"; g.shadowBlur = 18 + level * 60;
    g.fill(); g.shadowBlur = 0;
    // puntini: orbite libere, ma convergono al centro (caricamento) col pensiero
    // e cavalcano il bordo liquido mentre il modello parla
    const heard = mode === "heard" ? 1 : 0;
    const loading = mode === "thinking" ? 1 : 0;
    const riding = mode === "speaking" ? 1 : 0;
    for (const d of dots) {
      d.a += 0.003 * spin * (0.7 + d.r / R) + loading * 0.05;
      let target = heard ? R * 1.02 : d.base;
      if (loading) target = R * 0.22;                       // tutti al centro: caricamento
      if (riding) target = R + wave(d.a, t, amp);           // sul bordo liquido dell'orb
      d.r += (target - d.r) * 0.12;                         // ease: fluido, mai rigido
      const x = CX + d.r * Math.cos(d.a), y = CY + d.r * Math.sin(d.a);
      g.beginPath(); g.arc(x, y, d.s, 0, Math.PI * 2);
      g.fillStyle = `rgba(255,255,255,${Math.min(0.95, d.o + 0.15)})`;
      g.fill();
    }
    // increspature a ogni pacchetto audio ricevuto (sta parlando)
    ripples = ripples.filter(rp => rp.a > 0.02);
    for (const rp of ripples) {
      rp.r += 4; rp.a *= 0.94;
      g.beginPath(); g.arc(CX, CY, rp.r, 0, Math.PI * 2);
      g.strokeStyle = `rgba(179,52,31,${rp.a})`; g.lineWidth = 2; g.stroke();
    }
    // flash bianco all'interruzione, rosso in caso di errore
    if (flash > 0.02) {
      g.fillStyle = `rgba(255,255,255,${flash * 0.55})`;
      g.fillRect(0, 0, 520, 520); flash *= 0.88;
    }
    if (flashRed > 0.02) {
      g.fillStyle = `rgba(179,52,31,${flashRed * 0.35})`;
      g.fillRect(0, 0, 520, 520); flashRed *= 0.92;
    }
    requestAnimationFrame(draw);

  }
  requestAnimationFrame(draw);

  async function playLoop() {
    if (playing) return;
    playing = true; mode = "speaking"; setState("st_speaking");
    const actx = ctx;
    while (playQ.length && actx) {
      const chunk = playQ.shift(), n = chunk.byteLength / 2, dv = new DataView(chunk);
      const buf = actx.createBuffer(1, n, ttsRate), ch = buf.getChannelData(0);
      for (let i = 0; i < n; i++) ch[i] = dv.getInt16(i * 2, true) / 32768;
      const src = actx.createBufferSource();
      src.buffer = buf; src.connect(actx.destination); src.start(); curSrc = src;
      await new Promise((r) => { src.onended = r; });
    }
    curSrc = null; playing = false;
    if (live) { mode = "listening"; setState("st_listening"); }
  }
  function stopPlayback() {
    playQ = [];
    if (curSrc) { try { curSrc.stop(); } catch (e) { /* already stopped */ } }
  }

  // ---- booking summary pop-up: shown when a booking is made, closed 4 s after the caller's spoken
  // final "yes" (voice only: no button, no click). Also closed when the call ends.
  const TOAST_MS = 4000;
  let toastTimer = null;
  function showToast(m) {
    clearTimeout(toastTimer);
    const when = new Date(m.date + "T12:00:00");
    const day = isNaN(when) ? m.date : when.toLocaleDateString(LANG === "en" ? "en-GB" : "it-IT",
      { weekday: "long", day: "numeric", month: "long" });
    const n = Number(m.guests) || 0;
    $("toast-name").textContent = m.name || "";
    $("toast-name").hidden = !m.name;
    $("toast-when").textContent = day.charAt(0).toUpperCase() + day.slice(1) + " · " + String(m.time || "").slice(0, 5);
    $("toast-who").textContent = t(n === 1 ? "toast_guest_one" : "toast_guests", { n }) + (m.area ? " · " + m.area : "");
    $("toast-title").textContent = t(String(m.status).toUpperCase() === "CONFIRMED" ? "toast_confirmed" : "toast_updated");
    $("toast").hidden = false;
  }
  function hideToast() { clearTimeout(toastTimer); $("toast").hidden = true; }

  function onMessage(ev) {
    if (typeof ev.data !== "string") { ripples.push({ r: R + 10, a: 0.6 }); playQ.push(ev.data); playLoop(); return; }
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    switch (m.event) {
      case "ready":
        if (m.tts_sample_rate) ttsRate = m.tts_sample_rate;
        live = true; mode = "listening"; setState("st_listening"); break;
      case "loading": mode = "thinking"; setState("st_loading"); break;
      case "heard": mode = "heard"; setState("st_heard"); break;
      case "transcript": logLine("user", m.text); break;
      case "thinking": mode = "thinking"; setState("st_thinking"); break;
      case "reply": logLine("bot", m.text); break;
      case "barge_in": stopPlayback(); flash = 1; mode = "listening"; setState("st_listening"); break;
      case "registered": store.customer_id = m.customer_id; save(store); break;
      case "reservation":
        if (m.customer_id) { store.customer_id = m.customer_id; }
        upsert({ code: m.code, date: m.date, time: m.time, guests: Number(m.guests) || 0, status: m.status,
                 table: m.table, location: m.location });
        if (String(m.status).toUpperCase() === "CANCELLED") hideToast(); else showToast(m);
        break;
      case "reservation_confirmed": toastTimer = setTimeout(hideToast, TOAST_MS); break;  // the caller said the final yes
      case "error": flashRed = 1; setState("st_error", { d: (m.detail || "error") + (m.message ? " " + m.message : "") }); break;
      default: break;
    }
  }
  window.voiceSite = { handle: onMessage };  // lets a console / test feed server events to the page
  function connect() {
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/voice");
    ws.binaryType = "arraybuffer";
    ws.onopen = () => { retry = 0; };
    ws.onmessage = onMessage;
    ws.onerror = () => {};
    ws.onclose = () => {
      live = false;
      if (!wantLive) return;
      const delay = Math.min(500 * 2 ** retry, 8000); retry++;  // exponential backoff
      mode = "idle"; setState("st_retry", { s: (delay / 1000).toFixed(1) });
      retryTimer = setTimeout(connect, delay);
    };
  }
  async function start() {
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SR });
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: SR, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      const source = ctx.createMediaStreamSource(stream);
      proc = ctx.createScriptProcessor(2048, 1, 1);
      proc.onaudioprocess = (ev) => {
        const f = ev.inputBuffer.getChannelData(0);
        let s = 0; for (let i = 0; i < f.length; i++) s += f[i] * f[i];
        level = Math.min(1, Math.sqrt(s / f.length) * 6);
        const b = new ArrayBuffer(f.length * 2), dv = new DataView(b);
        for (let i = 0; i < f.length; i++) dv.setInt16(i * 2, Math.max(-32768, Math.min(32767, f[i] * 32768)), true);
        if (ws && ws.readyState === 1) ws.send(b);
      };
      source.connect(proc); proc.connect(ctx.destination);
      wantLive = true; retry = 0; setState("st_connecting"); connect();
    } catch (e) {
      setState("st_error", { d: String(e) });
    }
  }
  function hangUp() {
    const was = wantLive;
    wantLive = false; live = false; clearTimeout(retryTimer); stopPlayback(); level = 0; mode = "idle"; hideToast();
    try { if (ws) ws.close(); } catch (e) { /* closing */ }
    try { if (proc) proc.disconnect(); if (stream) stream.getTracks().forEach((x) => x.stop()); if (ctx) ctx.close(); } catch (e) { /* closing */ }
    ws = proc = stream = ctx = null;
    if (was) setState("st_ended");
  }
  orb.addEventListener("click", () => { if (wantLive) hangUp(); else start(); });
  orb.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); orb.click(); } });

  // ---------------------------------------------------------------- start
  (async function init() {
    let cfg = {};
    try { cfg = await getJson("/site/config"); } catch (e) { /* defaults */ }
    LANG = cfg.language === "en" ? "en" : "it";
    applyI18n();
    if (cfg.mode === "local") {
      const b = $("banner"); b.hidden = false; b.textContent = t("banner_local");
      $("assistant").classList.add("show-log");  // the live transcript is a test tool: only in local mode
    }
    renderReservations();
    loadInfo(); loadMenu();
    refreshAll();
  })();
})();
