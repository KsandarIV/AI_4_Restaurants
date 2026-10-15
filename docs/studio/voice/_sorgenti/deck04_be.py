from lib import *


def ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def table(head: list[str], rows: list[list[str]]) -> str:
    return "<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"


def build() -> Deck:
    d = Deck("04 · Il BE e i punti di contatto", "04_il_be_e_i_punti_di_contatto")
    d.cover("Il BE e dove il Voice lo incontra", "Cosa fa il backend, quali endpoint usiamo, cosa succede dentro a ogni richiesta e cosa chiedere al team BE")

    # ---------------------------------------------------------------- 2 BE in una pagina
    s = []
    s.append(box(10, 30, 210, 90, "VOICE / CHAT", fill=RED, stroke=DARK, color="#fff", size=20, sub="client"))
    s.append(box(300, 10, 300, 130, "FastAPI  /api", fill=BROWN, stroke=BROWN, color="#fff", size=22,
                 sub="routes.py · staff.py\nCORS aperto in LAN"))
    s.append(box(300, 190, 300, 150, "LangGraph", fill="#fff7ec", stroke=RED, size=22,
                 sub="agent → tools → agent\nconferma sì/no\ncheckpoint SQLite"))
    s.append(box(690, 190, 230, 150, "Ollama", fill="#fff", stroke=BROWN, size=22, sub="gemma4 locale\n(con strumenti)"))
    s.append(box(690, 10, 230, 130, "crud.py", fill="#fff", stroke=GOLD, size=22, sub="regole di business\n+ lock sui tavoli"))
    s.append(box(990, 10, 150, 130, "SQLite", fill=GOLD, stroke="#a98616", color="#fff", size=21, sub="restaurant.db"))
    s.append(box(990, 190, 150, 150, "conversations\n.db", fill="#fff", stroke=MUTED, size=19, sub="memoria per\nsession_id"))
    s.append(arrow(222, 75, 298, 75, "HTTP", ly=-8))
    s.append(arrow(450, 142, 450, 188, "process_message", lx=62, ly=0))
    s.append(arrow(602, 265, 688, 265, "LLM"))
    s.append(arrow(602, 75, 688, 75, "CRUD"))
    s.append(arrow(922, 75, 988, 75))
    s.append(arrow(922, 265, 988, 265))
    s.append(arrow(690, 190, 600, 140, "", dash=True))
    s.append(text(600, 395, "Il BE è l'unico che parla con l'LLM e con il database: i client sono «sottili».", 18, "600", "middle", DARK))
    d.add("Il BE in una pagina", svg(1152, 420, "".join(s)))

    # ---------------------------------------------------------------- 3 punti di contatto
    rows = [["<code>BackendClient.health_info()</code>", "GET <code>/api/health</code> (poi <code>/health</code>)", "database e modello rispondono davvero: online / degraded"],
            ["<code>register_customer()</code>", "POST <code>/api/customers</code>", "salva nome+telefono, restituisce <code>cust_…</code> (unico punto con dati personali)"],
            ["<code>chat()</code>", "POST <code>/api/chat</code>", "un turno intero (usato da v2 e dai referti)"],
            ["<code>stream_chat()</code>", "POST <code>/api/chat/stream</code>", "stessa cosa ma a token SSE; il BE <b>prima</b> esegue tutto il turno, poi manda le parole"],
            ["<code>get_reservation()</code>", "GET <code>/api/reservations/{codice}?customer_id=</code>", "solo il proprietario: gli altri ricevono 404"],
            ["server voice <code>/site/info</code>", "GET <code>/api/info</code>", "indirizzo, telefono, orari per il sito"],
            ["server voice <code>/site/menu</code>", "GET <code>/api/menu</code>", "menu con filtri (vegano, senza glutine…)"]]
    d.add("Dove il Voice tocca il BE", table(["Nel codice voice", "Endpoint del BE", "Cosa succede"], rows)
          + '<p class="small" style="margin-top:10px">Tutto passa da <code>voice/src/voicebot/backend.py</code> (httpx, retry, timeout) · il browser non parla mai direttamente col BE.</p>')

    # ---------------------------------------------------------------- 4 registrazione
    actors = [("Voice", RED), ("routes.py", BROWN), ("crud.py", BROWN), ("SQLite", GOLD)]
    steps = [(0, 0, "nome e telefono già validati (phonenumbers → E.164)"),
             (0, 1, "POST /api/customers {name, phone, consent:true}", True),
             (1, 1, "pydantic: telefono ^\\+[1-9]\\d{7,14}$, consenso obbligatorio"),
             (1, 2, "create_customer()"),
             (2, 3, "INSERT customers (customer_id = cust_…)"),
             (3, 2, "ok"), (2, 1, "{customer_id}"),
             (1, 0, "{customer_id}", True),
             (0, 0, "da ora il voice usa SOLO questo id: l'LLM non vede mai i dati")]
    d.add("Registrazione del cliente: l'unica volta con dati personali", seq(actors, steps, height=460, size=15))

    # ---------------------------------------------------------------- 5 turno di chat
    s = []
    s.append(box(10, 20, 250, 90, "POST /api/chat/stream", fill=RED, stroke=DARK, color="#fff", size=19, sub="messaggio + session_id\n+ customer_id"))
    s.append(box(320, 20, 250, 90, "Proposta in attesa\ne cliente dice «sì»?", fill="#fff7ec", stroke=GOLD, size=18))
    s.append(box(630, 20, 250, 90, "Domanda su\nallergie?", fill="#fff7ec", stroke=GOLD, size=18))
    s.append(box(940, 20, 200, 90, "LLM + strumenti", fill="#fff", stroke=BROWN, size=19, sub="agent_node"))
    s.append(arrow(262, 65, 318, 65))
    s.append(arrow(572, 65, 628, 65, "no", ly=-10))
    s.append(arrow(882, 65, 938, 65, "no", ly=-10))
    s.append(box(320, 190, 250, 90, "Esegue lo strumento", fill="#e3f3e8", stroke=GREEN, size=18, sub="lo fa il codice, non l'LLM"))
    s.append(box(630, 190, 250, 90, "Risposta dal codice", fill="#e3f3e8", stroke=GREEN, size=18, sub="costruita dal menu"))
    s.append(arrow(445, 112, 445, 188, "sì", lx=14, ly=0))
    s.append(arrow(755, 112, 755, 188, "sì", lx=14, ly=0))
    s.append(box(940, 190, 200, 90, "Modifica dati?", fill="#fdecea", stroke=RED, size=18, sub="create · modify · cancel"))
    s.append(arrow(1040, 112, 1040, 188))
    s.append(box(560, 330, 360, 80, "Riepilogo scritto dal CODICE", fill="#e3f3e8", stroke=GREEN, size=18, sub="«Confermi? sì o no» (pending_action)"))
    s.append(box(940, 330, 200, 80, "L'LLM risponde", fill="#fff", stroke=BROWN, size=18, sub="o legge menu / info"))
    s.append(arrow(990, 282, 800, 328, "sì", red=True, lx=-10, ly=-4))
    s.append(arrow(1090, 282, 1090, 328, "no", lx=16, ly=0))
    s.append(box(10, 330, 500, 80, "Il client riceve la risposta parola per parola", fill="#fff", stroke=MUTED, size=17, sub="SSE ogni 30 ms, poi data: [DONE]"))
    d.add("Dentro un turno di chat (backend/graph/workflow.py)", svg(1152, 430, "".join(s)))

    # ---------------------------------------------------------------- 6 conferma
    body = ('<div class="cols"><div class="col card red"><h2>Esempio</h2><pre>Cliente  vorrei un tavolo per due domani alle 20\n'
            'LLM      → propone create_reservation(...)\n'
            'CODICE   «Riepilogo: tavolo per 2 persone sabato 17\n'
            '          ottobre alle 20. Confermi? sì o no»\n'
            'Cliente  sì\n'
            'CODICE   esegue lo strumento → codice RES-9A8B2C\n'
            '\n'
            'Cliente  sì, ma alle 21     ← NON è una conferma:\n'
            '         il BE torna all\'LLM come modifica</pre></div>'
            '<div class="col card green"><h2>Perché è fatto così</h2>' + ul([
                "Un modello debole creava prenotazioni <b>fantasma</b> su saluti e frasi senza senso",
                "Una richiesta impossibile (giorno di chiusura, orario fuori turno, gruppo troppo grande) <b>non viene nemmeno proposta</b>",
                "<code>is_confirmation()</code>: vale solo se il messaggio è fatto <b>solo</b> di parole di conferma (≤ 4)",
                "Il voice fa lo stesso a valle: il suo referto finale e il suo «sì» sono <b>un secondo livello</b> di conferma, a voce"])
            + "</div></div>")
    d.add("Il protocollo di conferma: l'LLM propone, il codice esegue", body)

    # ---------------------------------------------------------------- 7 dati
    s = []
    tabs = [("tables", ["table_number", "capacity (posti)", "location: 3 ambienti", "is_active"], RED),
            ("reservations", ["booking_code (RES-…)", "customer_id", "table_id", "date · time · shift", "guests_count", "status prenotazione"], BROWN),
            ("customers", ["customer_id (cust_…)", "name", "phone (E.164)", "consent_at"], GREEN),
            ("menu_items", ["category · name · price", "allergens", "flag: veg · vegan · GF", "available (esaurito)"], GOLD),
            ("closures · info", ["closures: data + motivo", "restaurant_info:", "chiave → valore"], BLUE)]
    for i, (name, cols, col) in enumerate(tabs):
        x = 6 + i * 230
        s.append(f'<rect x="{x}" y="10" width="216" height="40" rx="8" fill="{col}"/>')
        s.append(text(x + 108, 36, name, 17, "700", "middle", "#fff"))
        for j, c in enumerate(cols):
            s.append(f'<rect x="{x}" y="{52 + j * 34}" width="216" height="32" fill="#fff" stroke="{LINE}"/>')
            s.append(text(x + 8, 74 + j * 34, c, 15, "400", "start", INK))
    s.append(box(6, 270, 1100, 120, "Regole in crud.py", fill="#fff7ec", stroke=GOLD, size=19,
                 sub="turno di 90 minuti: un tavolo è occupato se le finestre [ora, ora+90] si sovrappongono · tavolo più piccolo che basta (best fit)\n"
                     "pranzo 12:00–15:00 (ultima 14:00), cena 19:00–23:30 (ultima 22:00) · chiuso il lunedì · lock sull'allocazione dei tavoli"))
    d.add("Dati e regole di business", svg(1152, 410, "".join(s)))

    # ---------------------------------------------------------------- 8 LLM provider
    body = ('<div class="cols"><div class="col card brown"><h2>Scelta del modello (llm_provider.py)</h2>' + ul([
        "<code>OLLAMA_MODEL</code> può essere un elenco in ordine di preferenza + <code>OLLAMA_FALLBACK_MODELS</code>",
        "Si usa il <b>primo installato che sa usare gli strumenti</b> (<code>/api/show</code> → capabilities): senza strumenti non si prenota",
        "Nessun modello adatto → 503 con un messaggio chiaro, non un errore tecnico",
        "La scelta è nel log e in <code>/api/health</code>"]) + '</div><div class="col card gold"><h2>Velocità e robustezza</h2>' + ul([
            "<b>Thinking spento</b> di default (3–6 volte più veloce): <code>OLLAMA_REASONING</code>",
            "<b>Warm-up</b> all'avvio in un thread: il modello è già in memoria al primo cliente",
            "<code>OLLAMA_KEEP_ALIVE=30m</code>, timeout 120 s, temperatura 0,1",
            "<code>python -m backend.check_model</code>: 8 prove con OK/KO e tempi",
            "<code>health</code> = «online» solo se database E modello rispondono"]) + "</div></div>")
    d.add("L'LLM nel BE: scelta e velocità", body)

    # ---------------------------------------------------------------- 9 prompt e cache
    s = []
    parts = [("Regole fisse e lunghe", "ruolo, stile, menu solo da strumento, divieti", GREEN, 150),
             ("«Cliente NON registrato»", "blocco che cambia con la registrazione (righe 20–22)", RED, 66),
             ("Data odierna", "cambia ogni giorno (riga 43)", RED, 54),
             ("customer_id", "cambia per cliente (righe 48–50, 72)", RED, 60),
             ("Istruzioni degli strumenti", "usano il customer_id", GOLD, 90)]
    y = 10
    for name, sub, col, h in parts:
        s.append(f'<rect x="10" y="{y}" width="470" height="{h}" rx="10" fill="{col}" opacity="0.9"/>')
        s.append(text(245, y + h / 2 - 4, name, 18, "700", "middle", "#fff"))
        s.append(text(245, y + h / 2 + 18, sub, 14, "400", "middle", "#fff"))
        y += h + 6
    s.append(text(10, y + 20, "Oggi: appena cambia una riga rossa, l'LLM rilegge tutto il resto (cache persa).", 16, "600", "start", RED))
    s.append(box(560, 10, 580, 120, "Misurato su un portatile", fill="#fdecea", stroke=RED, size=20,
                 sub="primo turno di un cliente: 41–75 s · turni successivi: 1–5 s\nil modello legge ~36 token/s, scrive ~7 token/s"))
    s.append(box(560, 150, 580, 130, "Proposta per il BE", fill="#e3f3e8", stroke=GREEN, size=20,
                 sub="mettere data, stato di registrazione e customer_id\nin FONDO al prompt: la parte lunga resta in cache"))
    s.append(box(560, 300, 580, 130, "Cosa fa il Voice nel frattempo", fill="#fff", stroke=BROWN, size=20,
                 sub="id anonimo condiviso anon_voice · warm-up all'avvio ·\ncontesto limitato · nuova sessione ogni 20 scambi"))
    d.add("Il prompt del BE e la cache dell'LLM", svg(1152, 505, "".join(s)))

    # ---------------------------------------------------------------- 10 da chiedere
    rows = [["Alta", "L'endpoint <code>/api/chat/stream</code> è <code>async</code> ma chiama <code>process_message</code> in modo bloccante", "mentre l'LLM lavora il BE non risponde a nulla, nemmeno a <code>/api/health</code> (osservato: timeout di 10–20 s)"],
            ["Alta", "Spostare data / registrazione / customer_id in fondo al prompt", "cache dell'LLM intatta, primo turno per cliente da ~60 s a pochi secondi"],
            ["Alta", "Il modello a volte scrive «Chiamo get_menu…» invece di chiamare lo strumento", "il voice lo filtra, ma la causa è nel prompt/modello del BE"],
            ["Media", "Allineare il prompt vocale a <code>voice/src/voicebot/prompts.py</code>", "oggi il BE legge solo l'ultimo messaggio e usa il suo prompt"],
            ["Media", "Impostare <code>num_ctx</code> esplicito per il modello", "evita contesti da 64k su macchine con poca RAM"],
            ["Media", "Cognome solo se c'è già una prenotazione simile", "serve vedere le prenotazioni di altri: solo il BE può farlo, nel rispetto della privacy"],
            ["Bassa", "Endpoint «prenotazioni del cliente» (<code>/api/customers/{id}/reservations</code>)", "la pagina potrebbe elencarle tutte, non solo quelle di questo browser"]]
    d.add("Cosa chiedere al team BE", table(["Priorità", "Richiesta", "Perché"], rows))
    return d
