// Area ristoratore: prenotazioni (elenco, modifica, cancellazione), chiusure, piatti esauriti.
// Parla solo con l'area staff del BE (CONFIG.be.staffPath) con l'intestazione X-API-Key.
// Testi dei clienti sempre con textContent, mai come HTML.
(function () {
  const { be } = window.CONFIG;
  const $ = (id) => document.getElementById(id);
  const KEY_STORAGE = "staff_key";   // sessionStorage: sparisce alla chiusura della scheda
  let key = "";

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  };
  const today = () => {
    const d = new Date();
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  };
  const fmtDate = (iso) => (iso || "").split("-").reverse().join("/");

  // ---------- chiamate al BE ----------
  async function api(path, options) {
    options = options || {};
    let r;
    try {
      r = await fetch(be.baseUrl + be.staffPath + path, {
        method: options.method || "GET",
        headers: Object.assign({ "X-API-Key": key }, options.body ? { "Content-Type": "application/json" } : {}),
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: AbortSignal.timeout(15000),
      });
    } catch (e) {
      throw new Error("Non riesco a contattare il server. Controlla che il BE sia acceso.");
    }
    const data = await r.json().catch(() => ({}));
    if (r.status === 401) { const err = new Error("Chiave non valida."); err.auth = true; throw err; }
    if (r.status === 405 || (r.status === 404 && !data.detail)) throw new Error("Il BE in esecuzione non ha questa funzione: riavvialo con la versione aggiornata del codice.");
    if (!r.ok) throw new Error(data.detail || "Errore del server (" + r.status + ").");
    return data;
  }

  function say(id, text, kind) {
    const n = $(id);
    n.textContent = text || "";
    n.className = "msg-line" + (kind ? " " + kind : "");
  }
  const flash = (text, kind) => say("app-msg", text, kind);

  function onError(e) {
    if (e.auth) { logout("Chiave non valida: rientra."); return; }
    flash(e.message, "err");
  }

  // ---------- accesso ----------
  async function login(k) {
    key = k;
    try {
      await api("/closures");          // prova leggera: 401 se la chiave è sbagliata, 503 se l'area è disabilitata
    } catch (e) {
      key = "";
      say("login-msg", e.message, "err");
      return false;
    }
    try { sessionStorage.setItem(KEY_STORAGE, key); } catch (e) { /* storage non disponibile */ }
    $("login").hidden = true;
    $("app").hidden = false;
    $("logout").hidden = false;
    say("login-msg", "");
    $("key").value = "";
    loadReservations();
    return true;
  }

  function logout(message) {
    key = "";
    try { sessionStorage.removeItem(KEY_STORAGE); } catch (e) { /* ignora */ }
    $("app").hidden = true;
    $("logout").hidden = true;
    $("login").hidden = false;
    $("res-table").querySelector("tbody").replaceChildren();   // niente dati personali sullo schermo
    say("login-msg", message || "", message ? "err" : "");
  }

  $("login-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    login($("key").value.trim());
  });
  $("logout").addEventListener("click", () => logout());

  // ---------- schede ----------
  document.querySelectorAll(".staff-tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".staff-tabs button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    ["reservations", "closures", "menu"].forEach((t) => { $("tab-" + t).hidden = t !== b.dataset.tab; });
    flash("");
    if (b.dataset.tab === "reservations") loadReservations();
    if (b.dataset.tab === "closures") loadClosures();
    if (b.dataset.tab === "menu") loadMenu();
  }));

  // ---------- prenotazioni ----------
  async function loadReservations() {
    const q = new URLSearchParams();
    if ($("f-date").value) q.set("date", $("f-date").value);
    if ($("f-status").value) q.set("status", $("f-status").value);
    try {
      const list = await api("/reservations" + (q.toString() ? "?" + q : ""));
      renderReservations(list);
    } catch (e) { onError(e); }
  }

  function renderReservations(list) {
    const body = $("res-table").querySelector("tbody");
    body.replaceChildren();
    const active = list.filter((r) => r.status === "CONFIRMED");
    const covers = active.reduce((s, r) => s + r.guests_count, 0);
    $("res-count").textContent = list.length
      ? list.length + " prenotazioni (" + active.length + " confermate, " + covers + " coperti)"
      : "Nessuna prenotazione.";
    list.forEach((r) => {
      const tr = el("tr", r.status === "CANCELLED" ? "cancelled" : "");
      const table = r.table_number ? r.table_number + (r.table_location ? " (" + r.table_location + ")" : "") : "—";
      [fmtDate(r.date), r.time, r.guests_count, table, r.customer_name || "—", r.customer_phone || "—"]
        .forEach((v) => tr.append(el("td", "", v)));
      tr.append(el("td", "notes", r.special_requests || ""));
      const st = el("td", "status");
      st.append(el("span", "badge " + (r.status === "CONFIRMED" ? "ok" : "ko"), r.status === "CONFIRMED" ? "Confermata" : "Cancellata"));
      tr.append(st, el("td", "", r.booking_code));
      const act = el("td", "actions");
      if (r.status === "CONFIRMED") {
        const box = el("div", "row-actions");
        const edit = el("button", "mini", "Modifica");
        edit.type = "button";
        edit.onclick = () => openEdit(r);
        const del = el("button", "mini danger", "Cancella");
        del.type = "button";
        del.onclick = () => cancelReservation(r);
        box.append(edit, del);
        act.append(box);
      }
      tr.append(act);
      body.append(tr);
    });
  }

  async function cancelReservation(r) {
    const who = r.customer_name ? " di " + r.customer_name : "";
    if (!window.confirm("Cancellare la prenotazione " + r.booking_code + who + " (" + fmtDate(r.date) + " " + r.time + ")?")) return;
    try {
      await api("/reservations/" + encodeURIComponent(r.booking_code), { method: "DELETE" });
      flash("Prenotazione " + r.booking_code + " cancellata.", "ok");
      loadReservations();
    } catch (e) { onError(e); }
  }

  // ---------- modifica ----------
  const dlg = $("edit-dialog");
  let editing = null;

  function openEdit(r) {
    editing = r;
    $("e-code").textContent = r.booking_code;
    $("e-who").textContent = (r.customer_name || "Cliente") + (r.customer_phone ? " · " + r.customer_phone : "");
    $("e-date").value = r.date;
    $("e-time").value = r.time;
    $("e-guests").value = r.guests_count;
    $("e-notes").value = r.special_requests || "";
    say("e-msg", "");
    dlg.showModal();
  }

  $("e-cancel").addEventListener("click", () => dlg.close());
  $("edit-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!editing) return;
    const body = {};
    if ($("e-date").value !== editing.date) body.new_date = $("e-date").value;
    if ($("e-time").value !== editing.time) body.new_time = $("e-time").value;
    if (Number($("e-guests").value) !== editing.guests_count) body.new_guests = Number($("e-guests").value);
    if ($("e-notes").value !== (editing.special_requests || "")) body.new_requests = $("e-notes").value;
    if (!Object.keys(body).length) { dlg.close(); return; }
    try {
      await api("/reservations/" + encodeURIComponent(editing.booking_code), { method: "PATCH", body });
      dlg.close();
      flash("Prenotazione " + editing.booking_code + " aggiornata.", "ok");
      loadReservations();
    } catch (e) {
      if (e.auth) { dlg.close(); onError(e); } else say("e-msg", e.message, "err");   // es. nessun tavolo libero
    }
  });

  $("filters").addEventListener("submit", (ev) => { ev.preventDefault(); loadReservations(); });
  $("f-today").addEventListener("click", () => { $("f-date").value = today(); loadReservations(); });
  $("f-all").addEventListener("click", () => { $("f-date").value = ""; loadReservations(); });

  // ---------- chiusure ----------
  async function loadClosures() {
    try {
      const list = await api("/closures");
      const ul = $("closure-list");
      ul.replaceChildren();
      if (!list.length) { ul.append(el("li", "empty", "Nessuna chiusura straordinaria.")); return; }
      list.forEach((c) => {
        const li = el("li");
        li.append(el("span", "", fmtDate(c.date) + (c.reason ? " · " + c.reason : "")));
        const b = el("button", "mini", "Riapri");
        b.type = "button";
        b.onclick = async () => {
          try {
            await api("/closures/" + encodeURIComponent(c.date), { method: "DELETE" });
            flash("Riaperto il " + fmtDate(c.date) + ".", "ok");
            loadClosures();
          } catch (e) { onError(e); }
        };
        li.append(b);
        ul.append(li);
      });
    } catch (e) { onError(e); }
  }

  $("closure-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      const r = await api("/closures", { method: "POST", body: { date: $("c-date").value, reason: $("c-reason").value.trim() || null } });
      const affected = r.reservations_to_handle || [];
      flash(affected.length
        ? "Chiuso il " + fmtDate($("c-date").value) + ". Attenzione: ci sono " + affected.length + " prenotazioni già fatte (" + affected.join(", ") + "): vanno gestite a mano."
        : "Chiuso il " + fmtDate($("c-date").value) + ".", affected.length ? "err" : "ok");
      $("c-date").value = "";
      $("c-reason").value = "";
      loadClosures();
    } catch (e) { onError(e); }
  });

  // ---------- menu ----------
  async function loadMenu() {
    try {
      const items = await api("/menu");
      const box = $("menu-staff");
      box.replaceChildren();
      let cat = null;
      items.forEach((m) => {
        if (m.category !== cat) { cat = m.category; box.append(el("h3", "menu-cat", cat)); }
        const row = el("div", "menu-row" + (m.available ? "" : " off"));
        row.append(el("span", "name", m.name), el("span", "price", "€ " + Number(m.price).toFixed(2).replace(".", ",")));
        const b = el("button", "mini" + (m.available ? "" : " danger"), m.available ? "Segna esaurito" : "Torna disponibile");
        b.type = "button";
        b.onclick = async () => {
          try {
            await api("/menu/" + m.id, { method: "PATCH", body: { available: !m.available } });
            flash(m.name + (m.available ? ": esaurito." : ": di nuovo disponibile."), "ok");
            loadMenu();
          } catch (e) { onError(e); }
        };
        row.append(b);
        box.append(row);
      });
    } catch (e) { onError(e); }
  }

  // ---------- avvio ----------
  try {
    const saved = sessionStorage.getItem(KEY_STORAGE);
    if (saved) login(saved);
  } catch (e) { /* storage non disponibile */ }
})();
