// Parte "sito": menu e informazioni, letti dal BE (con testi di riserva se il BE non risponde).
(function () {
  const { be, fallbackInfo } = window.CONFIG;

  async function getJson(path) {
    const r = await fetch(be.baseUrl + path, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  // ---------- informazioni ----------
  function fillInfo(info) {
    document.querySelectorAll("[data-info]").forEach((n) => {
      const value = info[n.dataset.info];
      if (!value) return;
      n.textContent = value;
      if (n.dataset.link === "tel") n.href = "tel:" + value.replace(/[^\d+]/g, "");
      if (n.dataset.link === "mailto") n.href = "mailto:" + value;
    });
  }

  async function loadInfo() {
    try {
      fillInfo({ ...fallbackInfo, ...(await getJson(be.infoPath)) });
    } catch {
      fillInfo(fallbackInfo);
    }
  }

  // ---------- menu ----------
  let dishes = [];
  let activeCategory = "Tutti";

  function tags(d) {
    const t = [];
    if (d.is_vegan) t.push("vegano");
    else if (d.is_vegetarian) t.push("vegetariano");
    if (d.is_gluten_free) t.push("senza glutine");
    if (d.allergens) t.push("allergeni: " + d.allergens);
    return t.join(" · ");
  }

  function renderMenu() {
    const box = document.getElementById("menu-list");
    box.replaceChildren();
    const order = [];
    dishes.forEach((d) => { if (!order.includes(d.category)) order.push(d.category); });
    order.filter((c) => activeCategory === "Tutti" || c === activeCategory).forEach((cat) => {
      box.append(el("h3", "cat", cat));
      dishes.filter((d) => d.category === cat).forEach((d) => {
        const row = el("div", "dish");
        const left = el("div");
        left.append(el("div", "dish-name", d.name));
        if (d.description) left.append(el("div", "dish-desc", d.description));
        const tg = tags(d);
        if (tg) left.append(el("div", "dish-tags", tg));
        row.append(left, el("div", "dish-price", "€ " + Number(d.price).toFixed(2).replace(".", ",")));
        box.append(row);
      });
    });
  }

  function renderFilters() {
    const box = document.getElementById("menu-filters");
    box.replaceChildren();
    const cats = ["Tutti", ...new Set(dishes.map((d) => d.category))];
    cats.forEach((c) => {
      const b = el("button", "chip", c);
      b.type = "button";
      b.setAttribute("aria-pressed", String(c === activeCategory));
      b.onclick = () => { activeCategory = c; renderFilters(); renderMenu(); };
      box.append(b);
    });
  }

  async function loadMenu() {
    const box = document.getElementById("menu-list");
    try {
      dishes = await getJson(be.menuPath);
      if (!dishes.length) throw new Error("vuoto");
      renderFilters();
      renderMenu();
    } catch {
      box.textContent = "Il menu non è al momento disponibile. Riprova tra poco o chiedi all'assistente.";
    }
  }

  // Stato del BE, mostrato dall'assistente. Restituisce true/false.
  window.checkBackend = async function () {
    try { await getJson(be.healthPath); return true; } catch { return false; }
  };

  loadInfo();
  loadMenu();
})();
