from lib import *


def ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def table(head: list[str], rows: list[list[str]]) -> str:
    return "<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"


def build() -> Deck:
    d = Deck("02 · Flusso del codice", "02_flusso_del_codice")
    d.cover("Il flusso del codice Voice", "Dal microfono del browser alla risposta parlata: moduli, code, stati, privacy e punti di contatto con il BE")

    # ---------------------------------------------------------------- 2 mappa moduli
    s = []
    layers = [
        ("Trasporto", RED, "pipeline/server.py (FastAPI, WebSocket, /site/*)  ·  pipeline/session.py (VoiceSession: le 3 fasi)  ·  __main__.py (comandi)"),
        ("Audio", BROWN, "vad.py (energia / webrtc)  ·  stt.py (faster-whisper)  ·  tts.py (Piper)  ·  audio.py (PCM, frasi, speakable)"),
        ("Conversazione", RED, "orchestrator.py  ·  contacts.py (registrazione)  ·  anonymizer.py + pii.py  ·  toolguard.py  ·  messages.py  ·  prompts.py  ·  spoken.py"),
        ("Verso il BE", BROWN, "backend.py (httpx, retry, SSE)  ·  chat_service.py (alternativa: passa dal servizio CHAT)"),
        ("Strumenti", GOLD, "doctor.py + diagnostics.py  ·  local.py + devtools/stub_be.py  ·  live_client.py  ·  v2.py  ·  config.py  ·  logging_json.py"),
    ]
    for i, (a, col, b) in enumerate(layers):
        y = 6 + i * 92
        s.append(f'<rect x="0" y="{y}" width="1152" height="80" rx="12" fill="#fff" stroke="{col}" stroke-width="2"/>')
        s.append(f'<rect x="0" y="{y}" width="200" height="80" rx="12" fill="{col}"/>')
        s.append(text(100, y + 47, a, 20, "700", "middle", "#fff"))
        parts = b.split("  ·  ")
        half = (len(parts) + 1) // 2
        s.append(text(218, y + 33, "  ·  ".join(parts[:half]), 16, "400", "start", INK))
        s.append(text(218, y + 58, "  ·  ".join(parts[half:]), 16, "400", "start", INK))
    d.add("Mappa del codice: 5 livelli", svg(1152, 480, "".join(s)))

    # ---------------------------------------------------------------- 3 sequenza
    actors = [("Browser", MUTED), ("Server WS", RED), ("VAD", BROWN), ("STT", BROWN), ("Orchestrator", RED), ("BE", BROWN), ("TTS", GOLD)]
    steps = [(0, 1, "PCM 16 kHz"), (1, 2, "frame"), (2, 3, "utterance"), (3, 4, "testo"), (4, 4, "anonimizza"),
             (4, 5, "POST stream", True), (5, 4, "token SSE", True), (4, 4, "ripristina + filtra"), (4, 6, "frasi"),
             (6, 1, "audio PCM"), (1, 0, "audio + eventi")]
    d.add("Una chiamata, dall'orb al BE e ritorno", seq(actors, steps, height=500, size=16))

    # ---------------------------------------------------------------- 4 code
    s = []
    stages = [("WS reader", RED, 0), ("VAD", BROWN, 1), ("STT", BROWN, 2), ("LLM turn\n+ TTS", RED, 3), ("WS writer", RED, 4)]
    qs = ["audio_in_q", "segment_q", "text_q", "audio_out_q"]
    for name, col, i in stages:
        x = 6 + i * 250
        s.append(box(x, 70, 130, 90, name, fill=col, stroke=col, color="#fff", size=20))
        if i < 4:
            s.append(arrow(x + 132, 115, x + 248, 115))
            s.append(text(x + 190, 96, qs[i], 15, "600", "middle", BROWN))
    s.append(box(8, 250, 1060, 78, "Ogni coda è LIMITATA (backpressure): se il server è in ritardo si perde il frame più vecchio, mai memoria che cresce", fill="#fff7ec", stroke=GOLD, size=17))
    s.append(box(8, 350, 520, 110, "Barge-in (interruzione)", fill="#fdecea", stroke=RED, size=19,
                 sub="parlato ≥ 300 ms mentre il bot parla → annulla il turno,\nsvuota l'audio in coda, avvisa il client"))
    s.append(box(548, 350, 520, 110, "Contatore di generazione", fill="#e3f3e8", stroke=GREEN, size=19,
                 sub="ogni interruzione incrementa _gen: il lavoro\n«vecchio» si accorge di essere scaduto e si ferma"))
    s.append(arrow(821, 162, 821, 245, "", dash=True, red=True))
    d.add("VoiceSession: tre fasi collegate da code", svg(1152, 480, "".join(s)))

    # ---------------------------------------------------------------- 5 VAD
    s = []
    s.append(box(20, 40, 230, 90, "Silenzio", fill="#fff", stroke=BROWN, size=20, sub="in attesa"))
    s.append(box(400, 40, 260, 90, "Parlato in corso", fill=RED, stroke=DARK, color="#fff", size=20, sub="si accumula l'audio"))
    s.append(box(820, 40, 300, 90, "Utterance pronta", fill=GREEN, stroke=GREEN, color="#fff", size=20, sub="va al riconoscimento"))
    s.append(arrow(252, 70, 398, 70, "RMS ≥ 500", ly=-10, size=15))
    s.append(arrow(662, 70, 818, 70, "pausa ≥ 600 ms", ly=-10, size=15))
    s.append(arrow(820, 110, 662, 110, "ma ≥ 250 ms di voce", dash=True, ly=22, size=14))
    s.append(box(20, 190, 530, 130, "Regole", fill="#fff7ec", stroke=GOLD, size=19,
                 sub="soglia energia 500 · pausa 600 ms · voce minima 250 ms\nsegmento massimo 15 s (poi taglia comunque)"))
    s.append(box(590, 190, 530, 130, "Il bug che abbiamo risolto", fill="#fdecea", stroke=RED, size=19,
                 sub="il tempo si misura sull'audio ricevuto, non sul numero di frame:\nil browser manda 128 ms alla volta, il client Python 20 ms →\nprima la pausa era 6 volte troppo lunga"))
    s.append(text(576, 380, "Due classificatori, una sola macchina a stati: EnergyVAD (default, zero dipendenze) e WebRtcVADWrapper (opzionale)", 17, "400", "middle", MUTED))
    d.add("VAD: quando una persona ha finito di parlare", svg(1152, 420, "".join(s)))

    # ---------------------------------------------------------------- 6 STT/TTS
    left = ('<div class="card red"><h2>STT · faster-whisper</h2>' + ul([
        "Modello <b>small</b>, int8, CPU: caricato <b>una volta</b> e condiviso da tutte le sessioni",
        "<code>beam_size=1</code>, lingua dall'.env (italiano), <code>vad_filter=False</code> (il VAD è già nostro)",
        "Scarta i segmenti con <code>no_speech_prob ≥ 0.6</code> e le «allucinazioni» note di Whisper",
        "Un <b>lock</b>: una trascrizione alla volta; gira in un thread per non bloccare l'event loop",
        "Prompt iniziale <b>spento</b> di default: veniva ripetuto al posto del nome"]) + "</div>")
    right = ('<div class="card gold"><h2>TTS · Piper</h2>' + ul([
        "Voce <b>it_IT-riccardo-x_low</b> (onnxruntime), frequenza annunciata al client nell'evento <code>ready</code>",
        "<b>SentenceChunker</b>: i token del BE diventano frasi complete e Piper parla <b>appena la prima è pronta</b>",
        "<code>speakable()</code>: via markdown ed emoji; i codici diventano «R E S, 9 A 8 B…»",
        "<code>spoken.py</code>: numeri, date e orari a parole («alle venti e trenta»)",
        "API di Piper ≥ 1.3 gestita (la 1.8 installata rompeva il TTS)"]) + "</div>")
    d.add("Riconoscimento e sintesi: scelte e trucchi", f'<div class="cols"><div class="col">{left}</div><div class="col">{right}</div></div>')

    # ---------------------------------------------------------------- 7 orchestrator
    s = []
    s.append(box(10, 10, 250, 70, "Benvenuto", fill="#fff", stroke=BROWN, size=19, sub="«Come posso aiutarla?»"))
    s.append(box(10, 120, 250, 90, "Fase CHAT", fill=RED, stroke=DARK, color="#fff", size=21, sub="menu e info con anon_voice"))
    s.append(arrow(135, 82, 135, 118))
    s.append(box(330, 120, 270, 90, "Parla di prenotare?", fill="#fff7ec", stroke=GOLD, size=18, sub="wants_booking(testo)"))
    s.append(arrow(262, 165, 328, 165))
    s.append(box(330, 250, 270, 100, "Fase REGISTRAZIONE", fill=BROWN, stroke=BROWN, color="#fff", size=19, sub="nome + telefono, riepilogo, sì/no"))
    s.append(arrow(465, 212, 465, 248, "sì", ly=0, lx=14))
    s.append(box(680, 250, 250, 100, "POST /api/customers", fill="#fff", stroke=RED, size=18, sub="→ customer_id anonimo"))
    s.append(arrow(602, 300, 678, 300))
    s.append(box(680, 120, 250, 90, "Replay della richiesta", fill="#e3f3e8", stroke=GREEN, size=18, sub="anonimizzata, al BE"))
    s.append(arrow(805, 248, 805, 212))
    s.append(box(1000, 120, 150, 90, "Referto\nfinale", fill=GREEN, stroke=GREEN, color="#fff", size=18))
    s.append(arrow(932, 165, 998, 165))
    s.append(box(10, 250, 250, 100, "Contesto pieno", fill="#fdecea", stroke=RED, size=18, sub="20 scambi → nuova sessione BE"))
    s.append(arrow(135, 212, 135, 248, "", dash=True, red=True))
    s.append(text(576, 400, "Il BE decide tutto il resto (strumenti, conferma sì/no, allergie). Il voice decide solo QUANDO chiedere i dati di contatto.", 17, "400", "middle", MUTED))
    d.add("Orchestrator: le fasi della conversazione", svg(1152, 430, "".join(s)))

    # ---------------------------------------------------------------- 8 privacy
    rows = [["Nome e telefono", "dette a voce in fase REGISTRAZIONE", "<b>solo</b> <code>POST /api/customers</code> → tabella <i>customers</i>", "nulla: vede solo <code>cust_…</code>"],
            ["Frasi libere", "es. «sono Mario, il mio 333…»", "<code>anonymize()</code> → <code>[NOME_1]</code>, <code>[TELEFONO_1]</code> → BE", "segnaposto opachi"],
            ["Risposta del BE", "può contenere segnaposto", "<code>restore()</code> prima della voce (mai mezzo segnaposto detto)", "—"],
            ["Ultima rete", "tutto ciò che esce verso il BE", "<code>scrub_pii()</code>: regex senza stato su e-mail, telefono, CF, indirizzo", "—"],
            ["Log", "telefono nei log", "mascherato: solo i primi 4 caratteri + «***»", "—"]]
    body = table(["Dato", "Da dove nasce", "Dove può andare", "Cosa vede l'LLM"], rows)
    body += ('<div class="cols" style="margin-top:14px"><div class="col card green"><h2>Strati dell\'anonimizzatore</h2>'
             + ul(["1) regex per forme fisse (e-mail, CF, telefono, indirizzo)", "2) regex per le frasi che introducono un nome («a nome di…»)",
                   "3) spaCy <code>it_core_news_md</code> come rete di sicurezza (opzionale)"]) + "</div></div>")
    d.add("Privacy: dove vanno i dati personali", body)

    # ---------------------------------------------------------------- 9 turno col BE
    s = []
    s.append(box(10, 20, 240, 80, "stream_chat()", fill=BROWN, stroke=BROWN, color="#fff", size=19, sub="SSE dal BE"))
    s.append(box(310, 20, 330, 80, "Tieni la prima frase", fill="#fff7ec", stroke=GOLD, size=18, sub="almeno 40 caratteri"))
    s.append(box(700, 20, 220, 80, "Pulita?", fill="#fff", stroke=BROWN, size=19, sub="toolguard"))
    s.append(box(980, 20, 160, 80, "La dico", fill=GREEN, stroke=GREEN, color="#fff", size=19, sub="a token"))
    s.append(arrow(252, 60, 308, 60)); s.append(arrow(642, 60, 698, 60)); s.append(arrow(922, 60, 978, 60, "sì", ly=-8))
    s.append(box(700, 160, 220, 90, "Riprova 1 volta", fill="#fdecea", stroke=RED, size=18, sub="+ «usa subito gli strumenti»"))
    s.append(arrow(810, 102, 810, 158, "no", red=True, lx=14, ly=0))
    s.append(box(980, 160, 160, 90, "Frase neutra", fill="#fdecea", stroke=RED, size=17, sub="«non sono riuscito…»"))
    s.append(arrow(922, 205, 978, 205, "ancora no", red=True, ly=-8, size=12))
    s.append(box(10, 300, 1130, 120, "Cosa intercetta il filtro", fill="#fff", stroke=MUTED, size=19,
                 sub="nomi di strumenti (get_menu…) · «devo prima chiamare…» · «vuole che verifichi…?» ·\n«Posso mostrarle i piatti…» detto al posto di mostrarli"))
    d.add("Il turno col BE: il filtro sulle risposte", svg(1152, 440, "".join(s)))

    # ---------------------------------------------------------------- 10 report finale
    s = []
    s.append(box(10, 10, 270, 80, "Il BE conferma", fill=BROWN, stroke=BROWN, color="#fff", size=18, sub="nel testo c'è RES-XXXXXX"))
    s.append(box(340, 10, 330, 80, "GET /api/reservations/{code}", fill="#fff", stroke=RED, size=17, sub="solo il proprietario (altrimenti 404)"))
    s.append(box(730, 10, 400, 80, "Referto detto A VOCE", fill=RED, stroke=DARK, color="#fff", size=18, sub="costruito dal codice, non dall'LLM"))
    s.append(arrow(282, 50, 338, 50)); s.append(arrow(672, 50, 728, 50))
    s.append(box(10, 150, 540, 100, "«Sì» breve (≤ 6 parole, senza «ma»/numeri)", fill="#e3f3e8", stroke=GREEN, size=18,
                 sub="→ evento reservation_confirmed → il popup si chiude dopo 4 s"))
    s.append(box(590, 150, 540, 100, "«Sì, ma alle 21»", fill="#fff7ec", stroke=GOLD, size=18,
                 sub="NON è una conferma: va al BE come richiesta di modifica"))
    s.append(box(10, 290, 540, 100, "«No»", fill="#fdecea", stroke=RED, size=18, sub="«Mi dica cosa vuole cambiare»"))
    s.append(box(590, 290, 540, 100, "Eventi verso la pagina", fill="#fff", stroke=BROWN, size=18,
                 sub="reservation (nome, data, ora, persone, ambiente se chiesto)\nregistered · reservation_confirmed · call_ended"))
    d.add("Referto finale e conferma vocale", svg(1152, 420, "".join(s)))

    # ---------------------------------------------------------------- 11 contesto
    left = ('<div class="problem"><div class="lbl-red">Problema</div>Il BE tiene tutto il dialogo come contesto dell\'LLM: con un modello locale '
            'su CPU più contesto = più lento; il BE inoltre scrive data e <code>customer_id</code> in cima al prompt, quindi ogni nuovo id fa rileggere tutto.</div>'
            '<div class="fix"><div class="lbl-green">Cosa fa il voice</div>' + ul([
                "<b>20 scambi</b> senza arrivare a una prenotazione → nuova sessione BE + recap parlato",
                "Al <b>3° ripristino</b> avvisa («potrei dover ricominciare»); al <b>4°</b> chiude la chiamata (evento <code>call_ended</code>)",
                "Prenotazione raggiunta → contatori a zero; dopo il «sì» finale sessione nuova",
                "Cliente resta registrato: nessuno ripete nome e telefono"]) + "</div>")
    right = ('<div class="card gold"><h2>Prestazioni su portatile</h2>' + ul([
        "<b>Warm-up</b> all'avvio: un turno finto al BE, così il primo cliente non aspetta ~1 minuto",
        "Id anonimo <b>condiviso</b> <code>anon_voice</code>: stessa cache del prompt per tutti gli anonimi",
        "Modello con contesto 8k e 6 thread (<code>voice/local_llm/Modelfile</code>)",
        "Misurato: primo turno ~41–70 s, poi 1–5 s"]) + "</div>")
    d.add("Contesto, cache e prestazioni", f'<div class="cols"><div class="col">{left}</div><div class="col">{right}</div></div>')

    # ---------------------------------------------------------------- 12 protocollo WS
    rows = [["↑ binario", "PCM16 mono 16 kHz", "browser: blocchi da 2048 campioni (128 ms) · client Python: 20 ms"],
            ["↑ testo", "{\"cmd\":\"eos\"} · {\"cmd\":\"reset\"}", "fine flusso · «nuova conversazione»"],
            ["↓ binario", "PCM16 al tts_sample_rate (22050)", "l'audio del bot, a pezzi, frase per frase"],
            ["↓ eventi", "loading · ready · heard · transcript · thinking · reply · barge_in", "stati della chiamata per l'interfaccia"],
            ["↓ eventi", "registered · reservation · reservation_confirmed · call_ended · error", "fatti strutturati: popup, «Le mie prenotazioni», fine chiamata"]]
    body = table(["Verso", "Contenuto", "Note"], rows)
    body += '<p class="small" style="margin-top:12px">Indirizzo: <code>ws://HOST:8003/ws/voice</code> · timeout di inattività 60 s · un solo socket per chiamata.</p>'
    d.add("Protocollo WebSocket /ws/voice", body)

    # ---------------------------------------------------------------- 13 sito e orb
    left = ('<div class="card red"><h2>Pagine servite dal server voice</h2>' + ul([
        "<code>/</code> il sito: menu, info, «Le mie prenotazioni», orb, chat",
        "<code>/test-voice</code> pagina di test con tab TECNICA / STATO, trascrizione ed eventi",
        "<code>/site/menu · info · reservation/{codice}</code>: il browser non parla mai col BE, passa da qui",
        "<code>/site/chat/*</code> → servizio CHAT (spento qui)",
        "<code>/health · /ready · /diag</code>"]) + "</div>")
    right = ('<div class="card gold"><h2>L\'orb parla da solo</h2>' + ul([
        "<b>Pallini bianchi</b> che vanno al centro = il BE sta pensando",
        "<b>Anello dorato</b> sottile e lento = a riposo",
        "Anello che <b>si ispessisce</b> con la fascia chiara che cresce = sta per parlare",
        "Anello che <b>ondeggia</b> (non in sincrono con l'orb) = sta parlando",
        "<b>Popup</b> di riepilogo: si chiude 4 s dopo il «sì» finale, solo a voce"]) + "</div>")
    d.add("Il sito e l'interfaccia", f'<div class="cols"><div class="col">{left}</div><div class="col">{right}</div></div>')

    # ---------------------------------------------------------------- 14 resilienza
    rows = [["BE irraggiungibile", "retry con backoff esponenziale", "se fallisce: frase parlata «non riesco a raggiungere il server»"],
            ["Timeout in lettura su POST", "<b>mai ritentato</b>", "la richiesta potrebbe essere già stata eseguita: niente doppioni"],
            ["Stream interrotto", "riconnessione solo prima del primo token", "dopo, si chiude: riprovare ripeterebbe parole"],
            ["Rete del client", "live_client / pagina: riconnessione con backoff", "la chiamata sopravvive a una caduta"],
            ["Modelli non pronti", "evento <code>loading</code>, attesa fino a 120 s", "il caricamento parte all'avvio (PRELOAD_MODELS)"],
            ["Errori tecnici", "mai letti ad alta voce", "sempre una frase breve e gentile"]]
    d.add("Resilienza: cosa succede quando qualcosa va storto", table(["Situazione", "Cosa facciamo", "Perché"], rows))
    return d
