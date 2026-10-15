from lib import *


def ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def build() -> Deck:
    d = Deck("01 · Stack tecnologico", "01_stack_tecnologico")
    d.cover("Stack tecnologico", "Ambiente (venv), rete (LAN) e componente Voice: cosa usiamo, come funziona e perché l'abbiamo scelto")

    # ---------------------------------------------------------------- 2 sistema
    s = []
    s.append(box(30, 20, 300, 60, "Browser del cliente", fill="#fff", stroke=MUTED, size=17, sub="Web Audio API + WebSocket"))
    s.append(box(30, 190, 300, 170, "VOICE  :8003", fill=RED, stroke=DARK, color="#fff", size=22,
                 sub="FastAPI + WebSocket\nVAD → STT → LLM → TTS"))
    s.append(box(430, 190, 300, 170, "BE  :8000", fill=BROWN, stroke=BROWN, color="#fff", size=22,
                 sub="FastAPI + LangGraph\nSQLite + Ollama"))
    s.append(box(830, 190, 290, 170, "CHAT  :8501 / :8002", fill=GOLD, stroke="#a98616", color="#fff", size=21,
                 sub="Streamlit + API del sito\nspaCy (anonimizzatore)"))
    s.append(box(430, 410, 300, 70, "Ollama · gemma4", fill="#fff", stroke=BROWN, size=18, sub="LLM 100% locale"))
    s.append(box(830, 20, 290, 60, "Sito vetrina  :8080", fill="#fff", stroke=MUTED, size=17, sub="frontend/ (HTML + JS)"))
    s.append(arrow(180, 82, 180, 188, "audio PCM + eventi (WebSocket)", red=True, lx=100))
    s.append(arrow(332, 275, 428, 275, "HTTP + SSE", red=True, ly=-10))
    s.append(arrow(828, 275, 732, 275, "HTTP JSON", ly=-10))
    s.append(arrow(580, 362, 580, 408, "LLM + tool call"))
    s.append(arrow(975, 82, 975, 188, "/chat/*"))
    s.append(arrow(830, 50, 600, 190, "menu / info", dash=True, lx=40, ly=-14))
    s.append(text(1000, 440, "Tre macchine sulla stessa rete (LAN).\nIl BE parte per primo e resta su.", 15, "400", "middle", MUTED))
    d.add("Il sistema in una pagina", svg(1152, 500, "".join(s)))

    # ---------------------------------------------------------------- 3 venv
    left = (
        '<div class="card brown"><h2>Un solo <span class="mono">.venv</span> alla radice del repo</h2>'
        + ul(["<b>base.txt</b> (sempre): fastapi, uvicorn[standard], httpx, pydantic, pydantic-settings, python-dotenv",
              "<b>be.txt</b>: langchain, langgraph, langgraph-checkpoint-sqlite, langchain-ollama, sqlalchemy",
              "<b>chat.txt</b>: streamlit, requests, spacy, phonenumbers",
              "<b>voice.txt</b>: websockets, numpy, faster-whisper, piper-tts, onnxruntime, sounddevice, phonenumbers, "
              "webrtcvad-wheels <i>(opzionale)</i>",
              "<b>dev.txt</b>: pytest, pytest-asyncio, mypy"]) + "</div>")
    right = (
        '<div class="card green"><h2>Come resta coerente</h2>'
        + ul(["Ogni macchina installa <b>base + il suo ruolo</b> (venv leggero)",
              "<span class='mono'>.venv/.setup_state.json</span> salva lo <b>sha256</b> di ogni file requirements",
              "Se un collega cambia un file, al prossimo avvio <code>is_setup()</code> vede l'hash diverso e riparte da solo",
              "<code>--role all</code> = tutto, per sviluppo e test",
              "Pacchetti che richiedono compilatore C++ sono <b>opzionali</b>: se falliscono si va avanti con un avviso"]) + "</div>"
        '<p class="small" style="margin-top:10px">Python ≥ 3.10 (consigliato 3.11/3.12; qui 3.13.5). '
        'Il setup usa <b>solo la libreria standard</b>: funziona anche con un venv rotto.</p>')
    d.add("Ambiente: un venv condiviso, requisiti per ruolo", f'<div class="cols"><div class="col">{left}</div><div class="col">{right}</div></div>')

    # ---------------------------------------------------------------- 4 setup flow
    s = []
    steps = [("1  Controllo Python", "≥ 3.10"), ("2  Crea .venv", "se manca"), ("3  pip install", "pacchetto per pacchetto,\noutput live"),
             ("4  Editable install", "pip install -e voice"), ("5  Modelli", "spaCy · Piper · Ollama"), ("6  Scrive lo stato", "hash dei requirements")]
    x = 10
    for i, (a, b) in enumerate(steps):
        s.append(box(x, 30, 180, 130, a, fill="#fff" if i % 2 == 0 else "#fff7ec", stroke=RED if i in (2, 4) else BROWN, size=17, sub=b))
        if i < len(steps) - 1:
            s.append(arrow(x + 182, 95, x + 188, 95))
        x += 190
    s.append(box(10, 220, 560, 130, "Se un pacchetto richiesto fallisce", fill="#fdecea", stroke=RED, color=INK, size=20,
                 sub="il setup si ferma con il nome del pacchetto\ne riparte da lì: i passi già fatti si saltano"))
    s.append(box(590, 220, 550, 130, "Se un pacchetto OPZIONALE fallisce", fill="#e3f3e8", stroke=GREEN, color=INK, size=20,
                 sub="es. webrtcvad senza compilatore C++ → avviso e si continua:\nil VAD a energia è il default"))
    s.append(text(576, 410, "Download dei modelli: voce Piper italiana da Hugging Face (~28 MB) in voice/models/ ·\n"
                  "modello spaCy it_core_news_md (solo CHAT) · Ollama: ollama pull del modello (solo BE)", 17, "400", "middle", MUTED))
    d.add("setup/setup_env.py: cosa fa, in ordine", svg(1152, 470, "".join(s)))

    # ---------------------------------------------------------------- 5 entrypoint
    s = []
    flow = ["git pull --ff-only", "Identità: ruolo + IP", "Setup venv (per ruolo)", ".env di macchina", "Firewall (netsh)", "Attesa del BE", "Avvio componente"]
    for i, f in enumerate(flow):
        y = 8 + i * 66
        s.append(box(10, y, 330, 52, f"{i + 1}  {f}", fill="#fff7ec" if i % 2 else "#fff", stroke=RED if i in (1, 5) else BROWN, size=18))
        if i < len(flow) - 1:
            s.append(arrow(175, y + 53, 175, y + 65))
    s.append(box(420, 8, 330, 78, "git: solo fast-forward", fill="#fff", stroke=MUTED, size=18, sub="mai merge automatici sporchi"))
    s.append(box(420, 100, 330, 78, "lan/macchina.json", fill="#fff", stroke=MUTED, size=18, sub="ruolo + IP rilevato (socket UDP)"))
    s.append(box(420, 192, 330, 78, ".env generato da .env.example", fill="#fff", stroke=MUTED, size=17, sub="BACKEND_BASE_URL=http://IP-BE:8000"))
    s.append(box(420, 284, 330, 78, "Firewall", fill="#fff", stroke=MUTED, size=18, sub="regola TCP in ingresso per ogni porta"))
    s.append(box(420, 376, 330, 78, "Cancello sul BE", fill="#fff", stroke=MUTED, size=18, sub="polling di /api/health ogni 2 s"))
    for y_from, y_to in ((34, 47), (100, 139), (232, 231), (298, 323), (364, 415)):
        s.append(line(342, y_from, 418, y_to, "#cdbba5", 1.5, True))
    s.append('<rect x="790" y="8" width="360" height="215" rx="12" fill="%s"/>' % BROWN)
    s.append(text(810, 40, "Comandi", 19, "700", "start", "#fff"))
    s.append(text(810, 70, "python entrypoint\\avvia.py\n--status    stato delle 3 macchine\n--attendi   il presentatore aspetta\n--sono      identifica e basta\n--no-git --no-wait --yes", 16, "400", "start", "#f6e9d6"))
    s.append(box(790, 245, 360, 150, "Avvio automatico", fill="#fff", stroke=GREEN, size=19,
                 sub="Scheduled Task al login +30 s:\nla macchina parte da sola"))
    d.add("entrypoint/avvia.py: un comando per macchina", svg(1152, 470, "".join(s)))

    # ---------------------------------------------------------------- 5b entrypoint: se un passo si ferma
    rows = [["1", "<code>git_pull()</code>", "<code>git pull --ff-only</code>", "si ferma e stampa l'errore: <b>non forzare</b>"],
            ["2", "<code>resolve_role()</code> · <code>ensure_identity()</code>", "ruolo da <code>--role</code> / <code>LAN_ROLE</code> / <code>macchina.json</code> / domanda; IP rilevato", "lo chiede una sola volta"],
            ["3", "<code>ensure_environment(role)</code>", "confronta gli hash e installa solo se serve", "si ferma: rilanciare dopo aver sistemato"],
            ["4", "<code>configure_env()</code>", "scrive <code>BACKEND_BASE_URL</code>, <code>BE_URL</code>, <code>HOST</code> nel <code>.env</code>", "errore solo se manca <code>.env.example</code>"],
            ["5", "<code>firewall_hint()</code>", "<code>netsh advfirewall</code> per ogni porta del ruolo", "<b>non blocca</b>: stampa il comando da admin"],
            ["6", "<code>wait_for_be()</code>", "<code>GET /api/health</code> ogni 2 s, max 180 s (solo CHAT e VOICE)", "«BE assente»: il componente non parte"],
            ["7", "<code>start_component()</code>", "processo principale + servizi extra, log live", "<code>Ctrl+C</code> ferma tutto"]]
    t = "<table><tr><th>#</th><th>Funzione</th><th>Cosa fa</th><th>Se qualcosa va storto</th></tr>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"
    t += ('<p class="small" style="margin-top:12px">Codice: <code>entrypoint/avvia.py</code> (<code>main</code>) e <code>lan/machine_setup.py</code>. '
          '<code>--status</code> e <code>--attendi</code> usano gli IP di <code>lan_config.json</code>: con IP statici si fissano con <code>--pubblica-ip</code>.</p>')
    d.add("L'entrypoint nel dettaglio: funzione per funzione", t)

    # ---------------------------------------------------------------- 6 LAN table
    rows = [("BE", "backend/", "8000", "/api/health", "+ sito vetrina :8080 (http.server su frontend/)"),
            ("CHAT", "chat/", "8501 (Streamlit)", "/_stcore/health", "+ API del sito :8002 (uvicorn chat/api.py)"),
            ("VOICE", "voice/", "8003", "/health", "WebSocket /ws/voice · sito / · test /test-voice")]
    t = "<table><tr><th>Ruolo</th><th>Cartella</th><th>Porta</th><th>Health</th><th>Servizi aggiuntivi</th></tr>" + "".join(
        f"<tr><td><b>{a}</b></td><td><code>{b}</code></td><td>{c}</td><td><code>{e}</code></td><td>{f}</td></tr>" for a, b, c, e, f in rows) + "</table>"
    body = t + ('<div class="cols" style="margin-top:18px"><div class="col card red"><h2>Regole di avvio</h2>'
                + ul(["Ordine: <b>BE → CHAT → VOICE</b> (<code>ordine_avvio</code> in lan_config.json)",
                      "CHAT e VOICE <b>non partono</b> finché il BE non risponde (gate di 180 s)",
                      "Tutto è dichiarato in <code>lan/lan_config.json</code>: comando, cwd, porte, health, variabili"])
                + '</div><div class="col card gold"><h2>Perché così</h2>'
                + ul(["Gli IP in lan_config.json sono <b>esempi</b>: quelli veri si chiedono una volta e si ricordano in macchina.json (non in git)",
                      "Così il giorno della demo il presentatore tocca <b>un solo PC</b>: <code>avvia.py --attendi</code>"])
                + "</div></div>")
    d.add("LAN: ruoli, porte e cancello sul BE", body)

    # ---------------------------------------------------------------- 7 voice stack
    s = []
    layers = [("Browser / client", "Web Audio API (ScriptProcessor, 2048 campioni) · WebSocket · canvas (orb)\nlive_client: microfono e altoparlante con sounddevice", "#fff"),
              ("Trasporto", "FastAPI 0.143 + uvicorn 0.54 · websockets 16\nasyncio.Queue con dimensione massima (backpressure)", "#fff7ec"),
              ("Audio locale", "VAD a energia RMS (opzionale webrtcvad) · faster-whisper 1.2.1 (CTranslate2): small, int8, CPU\nPiper 1.8 + onnxruntime 1.31 · voce italiana it_IT-riccardo-x_low", "#fff"),
              ("Conversazione", "orchestrator · contacts (phonenumbers) · anonymizer (regex + spaCy 3.8)\ntoolguard · prompt in italiano · messages / spoken (numeri e date a parole)", "#fff7ec"),
              ("Client del BE", "httpx 0.28 asincrono · retry con backoff · SSE (/api/chat/stream)\npydantic-settings per la configurazione (.env)", "#fff"),
              ("Qualità", "pytest 9 + pytest-asyncio · mypy strict (29 file) · log JSON strutturati\ndoctor / diag · Dockerfile multi-stage, utente non-root, healthcheck", "#fff7ec")]
    for i, (a, b, fill) in enumerate(layers):
        y = 6 + i * 78
        s.append(f'<rect x="0" y="{y}" width="1152" height="70" rx="12" fill="{fill}" stroke="{BROWN}" stroke-width="1.6"/>')
        s.append(f'<rect x="0" y="{y}" width="220" height="70" rx="12" fill="{RED if i in (2, 3) else BROWN}"/>')
        s.append(text(110, y + 41, a, 19, "700", "middle", "#fff"))
        s.append(text(238, y + 29, b, 16, "400", "start", INK))
    d.add("Voice: lo stack a strati", svg(1152, 480, "".join(s)))

    # ---------------------------------------------------------------- 8 qualità
    k = lambda n, l: f'<div class="card kpi"><div class="big">{n}</div><div class="lbl">{l}</div></div>'
    body = ('<div class="cols">' + "".join(f'<div class="col">{k(n, l)}</div>' for n, l in
                                          [("192", "test automatici (voice)"), ("29", "file con mypy --strict"), ("12", "controlli del doctor"), ("3", "ruoli: be · chat · voice")])
            + '</div><div class="cols" style="margin-top:20px"><div class="col card green"><h2>Come proviamo senza il resto del sistema</h2>'
            + ul(["<b>Stub BE</b> (voicebot/devtools/stub_be.py): un BE finto con registrazione, conferma sì/no, modifica, cancellazione",
                  "Test <b>ermetici</b>: conftest isola dal .env e spiega l'interprete sbagliato",
                  "<code>voice local</code>: stub + server + browser con un comando"])
            + '</div><div class="col card red"><h2>Come capiamo cosa non va</h2>'
            + ul(["<code>python -m voicebot doctor</code>: python, .env, pacchetti, modelli, audio, porta, BE, registrazione",
                  "<code>/diag</code> e tab STATO della pagina di test mostrano lo stesso report",
                  "Log JSON a una riga: facili da filtrare"]) + "</div></div>")
    d.add("Qualità: test, tipi e diagnosi", body)

    # ---------------------------------------------------------------- 9 decisioni
    rows = [("Tutto locale (Ollama, Whisper, Piper)", "API cloud", "Vincolo di progetto: nessun dato personale fuori dalla rete"),
            ("Un venv, requisiti per ruolo + hash", "Un requirements.txt unico", "Evita conflitti di merge e installazioni pesanti inutili"),
            ("Setup e LAN in sola stdlib", "Script con dipendenze", "Funzionano anche quando il venv è rotto"),
            ("asyncio con code limitate", "Thread / code illimitate", "Barge-in e backpressure semplici, niente memoria che cresce"),
            ("VAD a energia di default", "webrtcvad obbligatorio", "Zero dipendenze compilate su Windows"),
            ("Whisper small (non tiny)", "tiny (più veloce)", "tiny sbaglia numeri e nomi: per prenotare non basta"),
            ("Pacchetti opzionali tollerati", "Setup che si blocca", "Un compilatore C++ mancante non deve fermare la demo")]
    t = "<table><tr><th>Scelta</th><th>Alternativa scartata</th><th>Perché</th></tr>" + "".join(
        f"<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td></tr>" for a, b, c in rows) + "</table>"
    d.add("Decisioni di stack e motivi", t)

    # ---------------------------------------------------------------- 10 comandi
    rows = [("Prima volta su una macchina", "python entrypoint\\avvia.py"),
            ("Solo il setup, per ruolo", "python setup\\setup_env.py --role voice --with-dev"),
            ("Verifica veloce (esce 0/1)", "python setup\\setup_env.py --check-only"),
            ("Test completo in locale (stub BE)", "voice\\voice local"),
            ("Voice contro il BE vero", "voice\\voice real   →  http://localhost:8003/test-voice"),
            ("Perché non funziona?", "python -m voicebot doctor"),
            ("Test + tipi", "cd voice  ·  python -m pytest tests -q  ·  python -m mypy src"),
            ("Stato delle tre macchine", "python entrypoint\\avvia.py --status")]
    t = "<table><tr><th>Cosa voglio fare</th><th>Comando</th></tr>" + "".join(
        f"<tr><td>{a}</td><td><code>{esc(b)}</code></td></tr>" for a, b in rows) + "</table>"
    d.add("Comandi da ricordare", t)
    return d
