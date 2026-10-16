// Trattoria Bella Napoli - voice site.
// Same kind of site as the chat bot's (menu, hours, assistant) plus "My reservations".
// Menu / info / reservation lookups go through THIS server (/site/*), never straight to the BE.
(function () {
  "use strict";

  // Normally the page is served by the voice server itself (same origin). The "complete site" of
  // showcase/ serves this very file from another machine and sets window.VOICE_BASE = "http://<voice-pc>:8003".
  const API = (window.VOICE_BASE || "").replace(/\/$/, "");
  const WS_BASE = API ? API.replace(/^http/, "ws") : (location.protocol === "https:" ? "wss://" : "ws://") + location.host;
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
      hero_title: "La cucina campana,\ncome a casa della nonna.",
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
      h_email: "Email", nav_contacts: "Contatti", nav_staff: "Area staff", contacts_title: "Contatti e servizi",
      staff_title: "Area staff", staff_text: "Per il personale del ristorante: consulta le prenotazioni, modificale o cancellale, chiudi il locale in una data e segna i piatti esauriti.",
      staff_button: "Accedi all'area staff", staff_note: "Serve la chiave di accesso del ristorante.", staff_footer: "Area ristoratore",
      footer_tag: "Cucina campana dal 1987", map_title: "Mappa del ristorante",
      assistant_title: "Assistente vocale", close: "Chiudi", orb_aria: "Tocca per avviare o terminare la conversazione",
      new_conversation: "Nuova conversazione", hang_up: "Termina",
      toast_confirmed: "Prenotazione confermata", toast_updated: "Prenotazione aggiornata",
      toast_guests: "{n} persone", toast_guest_one: "1 persona",
      chat_button: "Scrivi", book_by_chat: "Prenota in chat", chat_title: "Assistente in chat",
      chat_placeholder: "Scrivi qui il tuo messaggio…", chat_send: "Invia",
      chat_unreachable: "Il servizio chat non è disponibile in questo momento.",
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
      hero_title: "Campanian cooking,\njust like grandma's.",
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
      h_email: "Email", nav_contacts: "Contact", nav_staff: "Staff area", contacts_title: "Contact and services",
      staff_title: "Staff area", staff_text: "For the restaurant staff: check the reservations, change or cancel them, close the restaurant on a date and mark dishes as sold out.",
      staff_button: "Open the staff area", staff_note: "The restaurant's access key is required.", staff_footer: "Restaurateur area",
      footer_tag: "Campanian cooking since 1987", map_title: "Restaurant map",
      assistant_title: "Voice assistant", close: "Close", orb_aria: "Tap to start or end the conversation",
      new_conversation: "New conversation", hang_up: "Hang up",
      toast_confirmed: "Booking confirmed", toast_updated: "Booking updated",
      toast_guests: "{n} guests", toast_guest_one: "1 guest",
      chat_button: "Chat", book_by_chat: "Book by chat", chat_title: "Chat assistant",
      chat_placeholder: "Type your message here…", chat_send: "Send",
      chat_unreachable: "The chat service is not available right now.",
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
    document.querySelectorAll("[data-i18n-title]").forEach((n) => { n.title = t(n.dataset.i18nTitle); });
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
      dishes = await getJson(API + "/site/menu");
      if (!dishes.length) throw new Error("empty");
      renderFilters(); renderMenu();
    } catch (e) {
      $("menu-list").textContent = t("menu_unavailable");
    }
  }
  async function loadInfo() {
    try {
      const info = await getJson(API + "/site/info");
      document.querySelectorAll("[data-info]").forEach((n) => {
        const v = info[n.dataset.info];
        if (!v) return;
        n.textContent = v;
        if (n.dataset.link === "tel") n.href = "tel:" + String(v).replace(/[^\d+]/g, "");
        if (n.dataset.link === "mailto") n.href = "mailto:" + v;
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
      const d = await getJson(API + "/site/reservation/" + encodeURIComponent(code) + "?customer_id=" + encodeURIComponent(store.customer_id));
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

  const note = $("orb-note");
  function showNote(text) { note.textContent = text; note.hidden = !text; }
  function setState(key, vars) {
    const text = t(key, vars);
    $("state").textContent = text;  // read by screen readers only: the orb explains itself
    showNote(key === "st_error" ? text : "");
  }
  // The "book by voice" button turns into the orb while the call lasts; tapping the orb hangs up.
  const FLOAT = 18;  // px: the orb floats up and down by this much (keep in sync with @keyframes orb-float)
  const wrap = $("orb-wrap"), morph = $("morph"), fab = $("assistant-fab");
  let orbOn = false, birthT = 0, lastTarget = null, timers = [];
  const later = (fn, ms) => timers.push(setTimeout(fn, ms));
  const clearTimers = () => { timers.forEach(clearTimeout); timers = []; };
  function box(el, x, y, w, h, radius) {
    el.style.left = x + "px"; el.style.top = y + "px"; el.style.width = w + "px"; el.style.height = h + "px"; el.style.borderRadius = radius;
  }
  // Where the orb lives: bottom right, hooked to the lower edge of the red band. At the top of its float a third of the
  // orb is over the band, the rest stays below. If the band scrolls away the orb stays under the top bar.
  function orbTarget() {
    const S = Math.max(150, Math.min(235, window.innerWidth * 0.43, window.innerHeight * 0.32));  // canvas size on screen
    const D = S * (2 * R) / 520;  // visible diameter of the blob
    const ringHalf = S * 0.42;  // outer radius of the golden ring
    const band = document.querySelector(".hero").getBoundingClientRect().bottom;
    let cy = band + D / 6 + FLOAT;
    cy = Math.max(64 + ringHalf, Math.min(window.innerHeight - ringHalf - 8, cy));
    return { S, D, cx: window.innerWidth - 22 - ringHalf, cy };
  }
  function placeOrb() {
    const tg = orbTarget();
    lastTarget = tg;
    wrap.style.left = (tg.cx - tg.S / 2) + "px"; wrap.style.top = (tg.cy - tg.S / 2) + "px";
    wrap.style.width = tg.S + "px"; wrap.style.height = tg.S + "px";
    return tg;
  }
  let placing = false;
  function replace() { if (orbOn && !placing) { placing = true; requestAnimationFrame(() => { placing = false; placeOrb(); }); } }
  window.addEventListener("scroll", replace, { passive: true });
  window.addEventListener("resize", replace);

  function orbIn() {  // button -> orb
    clearTimers();
    const r = fab.getBoundingClientRect();
    const tg = placeOrb();
    morph.style.transition = "none";
    morph.classList.remove("expanded", "fading");
    box(morph, r.left, r.top, r.width, r.height, "999px");
    morph.style.opacity = "1";
    $("morph-label").textContent = fab.textContent.trim();
    morph.hidden = false; fab.style.visibility = "hidden"; orbOn = true;
    void morph.offsetWidth;
    morph.style.transition = "";
    morph.classList.add("expanded");
    box(morph, tg.cx - tg.D / 2, tg.cy - tg.D / 2, tg.D, tg.D, "50%");
    later(() => { wrap.classList.add("on"); startBirth(); }, 680);   // the canvas fades in over the circle
    later(() => morph.classList.add("fading"), 1000);                // the circle dissolves into the live orb
    later(() => { morph.hidden = true; }, 1700);
  }
  function orbOut() {  // orb -> button
    if (!orbOn) return;
    clearTimers();
    orbOn = false; birthT = 0;
    const tg = lastTarget || orbTarget();
    const r = fab.getBoundingClientRect();
    morph.style.transition = "none";
    morph.classList.remove("fading"); morph.classList.add("expanded");
    box(morph, tg.cx - tg.D / 2, tg.cy - tg.D / 2, tg.D, tg.D, "50%");
    morph.style.opacity = "1"; morph.hidden = false;
    void morph.offsetWidth;
    morph.style.transition = "";
    wrap.classList.remove("on");
    later(() => { morph.classList.remove("expanded"); box(morph, r.left, r.top, r.width, r.height, "999px"); }, 140);
    later(() => { fab.style.visibility = ""; morph.hidden = true; }, 1200);
  }
  function showOrb(on) { if (on) orbIn(); else orbOut(); }
  function startCall() {
    if (wantLive) return;
    if (!window.isSecureContext) { showNote(t("insecure", { p: location.port || "8003", h: location.host })); return; }
    showNote("");
    showOrb(true);
    start();
  }
  document.querySelectorAll("[data-open-assistant]").forEach((b) => b.addEventListener("click", startCall));

  // liquid orb, same animation as the test page (blob + orbiting dots + ripples + flashes)
  let flash = 0, flashRed = 0;
  // ---- orb liquido: blob seno/coseno + puntini orbitali ----
  const CX = 260, CY = 260, R = 150;
  // ---- golden ring: thin and slowly turning at rest; thickens with a widening light band when the bot is
  // about to speak (reply received, audio not started); ripples like a liquid edge, out of step with the orb, while it speaks
  const RING_R = R + 44;
  let ringW = 5, ringLight = 0.45, ringAmp = 0, ringSpin = 0, ringPhase = 0, preparingSince = 0;
  const ease = (cur, target, k) => cur + (target - cur) * k;
  function ringWave(theta, t) {  // different frequencies and phases than the orb's wave(): never in sync
    return Math.sin(2 * theta - t * 1.3) * 0.5 + Math.sin(4 * theta + t * 2.1 + 1.7) * 0.32 + Math.cos(7 * theta - t * 1.1) * 0.18;
  }
  function drawRing(t, now) {
    const preparing = preparingSince && mode !== "speaking" ? Math.min(1, (now - preparingSince) / 1400) : 0;
    if (preparingSince && now - preparingSince > 9000) preparingSince = 0;  // reply without audio: do not stay thick
    const speaking = mode === "speaking";
    const bornT = birthT ? Math.max(0, Math.min(1, (now - birthT - 150) / 1900)) : 0;
    const grow = 1 - Math.pow(1 - bornT, 2.2);  // ease-out: it grows out from behind the orb, then settles and stays at its size
    ringW = ease(ringW, speaking ? 18 : 5 + 17 * preparing, 0.07);
    ringLight = ease(ringLight, speaking ? 0.7 : 0.45 + 0.4 * preparing, 0.07);
    ringAmp = ease(ringAmp, speaking ? 13 : 0, 0.06);
    ringSpin += (speaking ? 0.012 : preparing ? 0.008 : 0.0035);
    ringPhase = ringSpin;
    const pts = [];
    for (let i = 0; i <= 160; i++) {
      const th = (i / 160) * Math.PI * 2;
      const rr = (R * 0.86 + (RING_R - R * 0.86) * grow) + ringAmp * ringWave(th + ringPhase * 0.4, t);
      pts.push([CX + rr * Math.cos(th), CY + rr * Math.sin(th)]);
    }
    const path = () => { g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.closePath(); };
    const shade = (a, b) => {  // a turning two-tone gradient, so the rotation is visible
      if (!g.createConicGradient) return a;
      const c = g.createConicGradient(ringPhase, CX, CY);
      c.addColorStop(0, a); c.addColorStop(0.5, b); c.addColorStop(1, a);
      return c;
    };
    if (grow <= 0) return;
    g.save(); g.globalAlpha = Math.min(1, grow * 2.5);
    g.lineJoin = "round";
    path(); g.lineWidth = ringW * (0.5 + 0.5 * grow); g.strokeStyle = shade("#7a5a14", "#a8821f"); g.stroke();            // thick dark gold edges
    path(); g.lineWidth = Math.max(1.5, ringW * ringLight * (0.5 + 0.5 * grow)); g.strokeStyle = shade("#f6dd8f", "#e3b84d"); g.stroke();  // light inside
    g.restore();
  }
  const dots = Array.from({ length: 16 }, (_, i) => {
    const base = R * (0.78 + Math.random() * 0.34);
    return {
      a: (i / 16) * Math.PI * 2, r: base, base,
      s: 3.5 + Math.random() * 2.5, o: 0.5 + Math.random() * 0.4, at: 0
    };
  });
  function startBirth() {  // the orb has just appeared: the ring grows from behind it, the dots are born inside it, one by one
    birthT = performance.now();
    for (const d of dots) { d.at = 250 + Math.random() * 1700; d.r = R * 0.04; d.a = Math.random() * Math.PI * 2; }
  }
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
    drawRing(t, tms);  // behind the orb: at birth it grows out from under it
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
      const born = birthT ? Math.min(1, (tms - birthT - d.at) / 500) : 0;
      if (born <= 0) { d.r = R * 0.04; continue; }
      d.a += 0.003 * spin * (0.7 + d.r / R) + loading * 0.05;
      let target = heard ? R * 1.02 : d.base;
      if (loading) target = R * 0.22;                       // tutti al centro: caricamento
      if (riding) target = R + wave(d.a, t, amp);           // sul bordo liquido dell'orb
      d.r += (target - d.r) * 0.12;                         // ease: fluido, mai rigido
      const x = CX + d.r * Math.cos(d.a), y = CY + d.r * Math.sin(d.a);
      g.beginPath(); g.arc(x, y, d.s, 0, Math.PI * 2);
      g.fillStyle = `rgba(255,255,255,${Math.min(0.95, d.o + 0.15) * born})`;
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
    if (typeof ev.data !== "string") { preparingSince = 0; ripples.push({ r: R + 10, a: 0.6 }); playQ.push(ev.data); playLoop(); return; }
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    switch (m.event) {
      case "ready":
        if (m.tts_sample_rate) ttsRate = m.tts_sample_rate;
        live = true; mode = "listening"; setState("st_listening"); break;
      case "loading": mode = "thinking"; setState("st_loading"); break;
      case "heard": mode = "heard"; setState("st_heard"); break;
      case "thinking": mode = "thinking"; setState("st_thinking"); break;
      case "reply": preparingSince = performance.now(); break;  // the bot is about to speak
      case "barge_in": stopPlayback(); preparingSince = 0; flash = 1; mode = "listening"; setState("st_listening"); break;
      case "registered": store.customer_id = m.customer_id; save(store); break;
      case "reservation":
        if (m.customer_id) { store.customer_id = m.customer_id; }
        upsert({ code: m.code, date: m.date, time: m.time, guests: Number(m.guests) || 0, status: m.status,
                 table: m.table, location: m.location });
        if (String(m.status).toUpperCase() === "CANCELLED") hideToast(); else showToast(m);
        break;
      case "call_ended": {  // the conversation ended the call: let the last sentence finish, then hang up
        const wait = setInterval(() => { if (!playing && !playQ.length) { clearInterval(wait); hangUp(); } }, 200);
        setTimeout(() => clearInterval(wait), 15000);
        break;
      }
      case "reservation_confirmed": toastTimer = setTimeout(hideToast, TOAST_MS); break;  // the caller said the final yes
      case "error": flashRed = 1; setState("st_error", { d: (m.detail || "error") + (m.message ? " " + m.message : "") }); break;
      default: break;
    }
  }
  window.voiceSite = { handle: onMessage, orbIn, orbOut };  // lets a console / test feed server events to the page
  function connect() {
    ws = new WebSocket(WS_BASE + "/ws/voice");
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
      wantLive = false; showOrb(false);
      setState("st_error", { d: String(e) });
    }
  }
  function hangUp() {
    const was = wantLive;
    wantLive = false; live = false; clearTimeout(retryTimer); stopPlayback(); level = 0; mode = "idle"; hideToast(); preparingSince = 0;
    try { if (ws) ws.close(); } catch (e) { /* closing */ }
    try { if (proc) proc.disconnect(); if (stream) stream.getTracks().forEach((x) => x.stop()); if (ctx) ctx.close(); } catch (e) { /* closing */ }
    ws = proc = stream = ctx = null;
    showOrb(false);
    if (was) setState("st_ended");
  }
  orb.addEventListener("click", () => { if (wantLive) hangUp(); else start(); });
  orb.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); orb.click(); } });

  // ---------------------------------------------------------------- chat (the chat bot, through this server)
  // /site/chat/* only forwards to the CHAT service when CHAT_SERVICE_URL is set; otherwise it answers 503.
  const chatPanel = $("chat-panel"), chatMsgs = $("chat-msgs"), chatInput = $("chat-input");
  let chatSession = null;
  // The bot answers in Markdown: turned into DOM nodes (never innerHTML, the text stays safe). Same helper as frontend/js/assistant.js.
  function mdInline(parent, text) {
    text.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) parent.append(el("strong", "", part.slice(2, -2)));
      else if (part) parent.append(part.replace(/\*+/g, ""));
    });
  }
  function renderMarkdown(box, text) {
    let list = null;
    text.split("\n").forEach((raw) => {
      const line = raw.trim();
      const bullet = line.match(/^[*\-•]\s+(.*)/);
      if (bullet) {
        if (!list) { list = el("ul"); box.append(list); }
        const li = el("li"); mdInline(li, bullet[1]); list.append(li);
        return;
      }
      list = null;
      if (!line) return;
      const p = el("p"); mdInline(p, line.replace(/^#+\s*/, "")); box.append(p);
    });
  }
  function chatLine(who, text) {
    const m = el("div", "msg " + who);
    if (who === "bot") renderMarkdown(m, text); else m.textContent = text;
    chatMsgs.append(m);
    m.scrollIntoView({ block: "nearest" });
    return m;
  }
  async function chatPost(path, body) {
    let r;
    try {
      r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                              body: JSON.stringify(body || {}), signal: AbortSignal.timeout(130000) });
    } catch (e) { throw new Error(t("chat_unreachable")); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || t("chat_unreachable"));
    return d;
  }
  async function chatStart() {
    chatMsgs.replaceChildren(); chatSession = null;
    try { const d = await chatPost(API + "/site/chat/session"); chatSession = d.session_id; chatLine("bot", d.reply); }
    catch (e) { chatLine("error", e.message); }
  }
  function openChat() { chatPanel.hidden = false; if (!chatSession) chatStart(); chatInput.focus(); }
  document.querySelectorAll("[data-open-chat]").forEach((b) => b.addEventListener("click", openChat));
  $("chat-close").addEventListener("click", () => { chatPanel.hidden = true; });
  $("chat-reset").addEventListener("click", chatStart);
  $("chat-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = "";
    chatLine("user", text);
    const typing = chatLine("bot typing", "…");
    try {
      if (!chatSession) { const d = await chatPost(API + "/site/chat/session"); chatSession = d.session_id; }
      const d = await chatPost(API + "/site/chat/message", { session_id: chatSession, text });
      typing.remove(); chatLine("bot", d.reply);
    } catch (e) {
      typing.remove(); chatLine("error", e.message);
      if (/scadut|expired/i.test(e.message)) chatSession = null;
    }
  });

  // ---------------------------------------------------------------- start
  (async function init() {
    let cfg = {};
    try { cfg = await getJson(API + "/site/config"); } catch (e) { /* defaults */ }
    LANG = cfg.language === "en" ? "en" : "it";
    applyI18n();
    if (cfg.mode === "local") { const b = $("banner"); b.hidden = false; b.textContent = t("banner_local"); }
    renderReservations();
    loadInfo(); loadMenu();
    refreshAll();
  })();
})();
