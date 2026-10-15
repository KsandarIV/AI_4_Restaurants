from lib import *


def ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def table(head: list[str], rows: list[list[str]]) -> str:
    return "<table><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"


def pf(problem: str, fix: str, evidence: str = "") -> str:
    ev = f'<p class="small" style="margin-top:6px">{evidence}</p>' if evidence else ""
    return (f'<div class="problem"><div class="lbl-red">Problema</div>{problem}</div>'
            f'<div class="fix"><div class="lbl-green">Come l\'abbiamo risolto</div>{fix}</div>{ev}')


def build() -> Deck:
    d = Deck("03 · Storia, fix e decisioni", "03_storia_fix_e_decisioni")
    d.cover("Storia del progetto: problemi ricorrenti e come li abbiamo risolti",
            "Ricostruita dalla cronologia git: 90 commit in tre giorni, tre contributori, tre componenti")

    # ---------------------------------------------------------------- 2 numeri
    k = lambda n, l: f'<div class="card kpi"><div class="big">{n}</div><div class="lbl">{l}</div></div>'
    body = ('<div class="cols">' + "".join(f'<div class="col">{k(n, l)}</div>' for n, l in
                                          [("90", "commit"), ("3", "contributori"), ("3", "giorni (14–16 ottobre)"), ("192", "test del solo voice")])
            + '</div><div class="cols" style="margin-top:18px">'
            + '<div class="col card brown"><h2>Dimensioni (righe)</h2>' + table(["Parte", "Righe"], [
                ["voice (codice, pagine, sito)", "6.272"], ["voice (test)", "2.358"], ["backend", "2.809"], ["chat", "1.420"],
                ["frontend", "1.212"], ["lan + setup + entrypoint", "1.327"], ["test del backend", "1.738"]]) + "</div>"
            + '<div class="col card gold"><h2>Ritmo</h2>' + ul(["14/10: <b>39</b> commit — nascono i tre componenti", "15/10: <b>50</b> commit — setup per ruolo, entrypoint, sito, rifacimento del voice",
                                                                   "16/10: rifiniture (orb, popup, contesto)", "~21.000 righe aggiunte, ~4.000 tolte nel periodo"]) + "</div></div>")
    d.add("Il progetto in numeri", body)

    # ---------------------------------------------------------------- 3 timeline
    s = []
    lanes = [("14/10", 10, [("14:02", "anonimizzatore v1"), ("14:08", "voice v1:\nstruttura base"), ("14:32", "BE: turni da 90 min,\ncheckpoint SQLite"),
                            ("14:40", "setup venv\nautomatico"), ("16:20", "BE: registrazione\nclienti"), ("17:07", "LAN setup\n+ scheduler")]),
             ("15/10", 160, [("09:18", "BE: conferma\nsì / no"), ("10:19", "entrypoint\nunico"), ("10:56", "setup\nper ruolo"),
                             ("12:03", "pagina di test\nvoice"), ("16:02", "voice come\nla chat"), ("16:57", "sito + referto\nparlato")]),
             ("15-16/10\nsera", 310, [("17:24", "pagina originale\nripristinata"), ("sera", "registrazione pigra,\nprompt IT, popup"), ("sera", "contesto, warm-up,\nanello dorato"),
                                     ("16/10", "toolguard, orb-pulsante,\nchat, /test-voice")])]
    for name, y, items in lanes:
        s.append(text(8, y + 52, name, 19, "700", "start", DARK))
        s.append(line(140, y + 54, 1150, y + 54, "#cdbba5", 3))
        n = len(items)
        step = 1010 / n
        for i, (t, lab) in enumerate(items):
            cx = 140 + step * (i + 0.5)
            hot = any(w in lab for w in ("voice", "pagina", "orb", "sito"))
            s.append(f'<circle cx="{cx}" cy="{y + 54}" r="9" fill="{RED if hot else BROWN}"/>')
            s.append(text(cx, y + 28, t, 16, "700", "middle", MUTED))
            s.append(text(cx, y + 86, lab, 16, "500", "middle", INK))
    s.append(text(576, 450, "rosso = lavoro sul componente VOICE · marrone = BE, CHAT, setup e LAN", 16, "400", "middle", MUTED))
    d.add("Linea del tempo", svg(1152, 470, "".join(s)))

    # ---------------------------------------------------------------- 4 setup
    d.add("Ricorrente 1 · Setup del venv e conflitti di merge",
          pf("Un solo <code>requirements.txt</code> e <code>setup_env.py</code> toccati da più persone: <b>7 modifiche su 2 giorni</b>, "
             "commit come «mio setup: tenere questa versione» e «fix setup env dopo merge sbagliato»; installazioni pesanti su macchine che non servivano.",
             ul(["Cartella spostata e stabilizzata: <code>tools/env_setup</code> → <code>setup/</code>",
                 "<b>Requisiti per ruolo</b> (base, be, chat, voice, dev): un file per persona → niente conflitti",
                 "Stato in <code>.venv/.setup_state.json</code> con <b>hash sha256</b>: se un file cambia, il setup riparte da solo",
                 "Installazione <b>pacchetto per pacchetto</b> con output live e pacchetti opzionali tollerati",
                 "Guardia: il venv non può mai nascere fuori dalla repo"]),
             "Catena: b8c1712 (primo setup) → 1aa2df6 → 1c172bd → 58e1f38 → 5af2bf3 (fix dopo merge) → 3fc4dbb (per ruolo)"))

    # ---------------------------------------------------------------- 5 LAN
    d.add("Ricorrente 2 · Ogni macchina deve sapere chi è e dove sta il BE",
          pf("Tre PC, tre ruoli, IP che cambiano, avvio nell'ordine giusto, firewall: 7 modifiche a <code>lan/machine_setup.py</code> in due giorni "
             "(«fix su lan per dare i ruoli a ciascuna macchina»).",
             ul(["<b>Identità</b> della macchina in <code>lan/macchina.json</code> (ruolo + IP rilevato con un socket UDP, mai in git)",
                 "<b>Un solo comando</b>: <code>entrypoint/avvia.py</code> (git → identità → setup → .env → firewall → attesa BE → avvio)",
                 "<b>Cancello sul BE</b>: CHAT e VOICE aspettano che <code>/api/health</code> risponda",
                 "<b>Servizi extra</b> per ruolo in <code>lan_config.json</code> (API del sito :8002, frontend :8080) fermati insieme con Ctrl+C",
                 "<b>Avvio automatico</b> con Scheduled Task per la demo: il presentatore tocca un solo PC (<code>--attendi</code>)"]),
             "5c0ad2b (ruoli) → 96301d1 (entrypoint) → 3fc4dbb (identità) → d183fb2 → 81084e4 (servizi extra)"))

    # ---------------------------------------------------------------- 6 pipeline
    rows = [["TTS si rompeva", "Piper 1.8 ha cambiato API", "gestite sia le API ≤ 1.2 sia ≥ 1.3"],
            ["Voce con tono sbagliato", "frequenza del modello ignorata dal client", "annunciata nell'evento <code>ready</code>"],
            ["Prima chiamata lentissima", "STT/TTS ricaricati a ogni chiamata", "modelli condivisi e <b>precaricati</b> all'avvio"],
            ["Pausa 6 volte troppo lunga", "VAD contava i frame (il browser ne manda da 128 ms)", "tempo misurato sull'audio ricevuto"],
            ["Bot che non si lascia interrompere", "barge-in non annullava un turno in «thinking»", "contatore di generazione + rumore breve ignorato"],
            ["Prenotazioni doppie", "POST ritentato dopo un timeout in lettura", "<b>mai</b> ritentare una richiesta non idempotente"],
            ["Test che dipendevano dal PC", ".env e interprete della macchina", "conftest isola, stub BE, 119 test ermetici"]]
    d.add("Ricorrente 3 · La pipeline vocale col modello vero (cd1be40)", table(["Sintomo", "Causa", "Fix"], rows))

    # ---------------------------------------------------------------- 7 whisper
    d.add("Ricorrente 4 · Il parlato non è testo",
          pf("Whisper <b>tiny</b> sbaglia numeri e nomi; il suo «prompt iniziale» veniva ripetuto al posto del nome; «alle 20 e 30» diventava 20:00; "
             "una pausa dentro un numero di telefono spezzava la frase in due.",
             ul(["Modello <b>small</b> di default; il prompt è <b>spento</b> (f073570)",
                 "Cifre parlate normalizzate («tre tre tre…») e <b>frammenti uniti</b> tra una frase e l'altra",
                 "Telefono letto <b>cifra per cifra</b> e validato con <code>phonenumbers</code>",
                 "Il BE finto capisce «alle 20 e 30» (d18d33c, trovato in una prova col modello reale)",
                 "Numeri, date e orari <b>a parole</b> prima della sintesi; allucinazioni di Whisper scartate"])))

    # ---------------------------------------------------------------- 8 LLM piccoli
    d.add("Ricorrente 5 · I modelli piccoli sbagliano: l'LLM propone, il codice decide",
          pf("<b>llama3.2</b> chiamava <code>create_reservation</code> su saluti e frasi senza senso: prenotazioni fantasma; passava la stringa «null»; "
             "inventava piatti per le allergie. Oggi, con gemma4, annuncia gli strumenti invece di usarli.",
             ul(["<b>Conferma esplicita</b> (06d45e1): l'LLM può solo <i>proporre</i>; riepilogo scritto dal codice e azione solo dopo un «sì» intero («sì ma alle 21» non vale)",
                 "Argomenti «null»/«nessuna» trattati come assenti; prenotazione proposta solo se nei messaggi c'è una richiesta (3baf68c)",
                 "<b>Allergie</b>: risposta costruita dal codice dal menu, mai dal modello (c7c1599)",
                 "<b>Voice</b>: filtro <code>toolguard</code> sulla prima frase, un nuovo tentativo, poi frase neutra",
                 "Modello scelto automaticamente tra quelli installati che sanno usare gli strumenti (4c7f0a2)"])))

    # ---------------------------------------------------------------- 9 privacy
    d.add("Ricorrente 6 · La privacy decide l'architettura",
          pf("Nome e telefono servono al ristorante ma l'LLM non deve vederli; un nome usato come identificativo era già un dato personale.",
             ul(["<code>POST /api/customers</code> è l'<b>unico</b> punto con dati personali → <code>customer_id</code> anonimo (6f64a50)",
                 "Con la registrazione attiva solo il <b>proprietario</b> legge, modifica o cancella (404 per gli altri)",
                 "Nei tool il <code>customer_id</code> arriva <b>dalla sessione</b>, mai dal modello",
                 "Anonimizzatore della CHAT portato nel voice con gli <b>stessi segnaposto</b>; rete di sicurezza <code>scrub_pii</code>",
                 "Registrazione a voce <b>solo quando serve</b> (si parla di prenotare); retention: <code>maintenance purge</code> dopo 90 giorni"])))

    # ---------------------------------------------------------------- 10 docs drift
    rows = [[".env.example", "10 modifiche", "test_docs controlla che ogni variabile documentata esista davvero"],
            ["README_VOICE.md", "10 modifiche", "test che legge il README e verifica moduli e comandi citati"],
            ["Pagina di test", "riscritta e perdute le animazioni", "ripristinata dall'originale (55069b6): <b>estendere, non riscrivere</b>"],
            ["Comandi nei docs", "<code>voice\\voice</code> diventato «voiceoice»", "backslash mangiati da caratteri di controllo: ripristinati"],
            ["Branch", "lavoro rimasto su savov e non su main", "merge di recupero (27b67cc)"]]
    d.add("Ricorrente 7 · Docs e configurazione che si disallineano", table(["Cosa", "Cosa è successo", "Decisione"], rows))

    # ---------------------------------------------------------------- 11 ultimi giorni
    rows = [["Saluto troppo lungo e «avido»", "Saluto breve; nome e telefono solo quando si parla di prenotare, poi la richiesta riparte da sola"],
            ["Bot che rispondeva in inglese per via del prompt", "Prompt <b>in italiano</b>, lingua del cliente se la conosce"],
            ["Il cliente non vedeva cosa era stato prenotato", "Popup di riepilogo, chiuso 4 s dopo il «sì» finale (solo voce)"],
            ["Modello locale lento su portatile", "Contesto 8k, warm-up, id anonimo condiviso, 20 scambi poi nuova sessione, 4° giro chiude"],
            ["«Chiamo get_menu… vuole che verifichi?»", "Filtro sulla prima frase + un nuovo tentativo"],
            ["Orb senza segnali chiari", "Anello dorato: sottile/lento → si ispessisce → ondeggia mentre parla"],
            ["Pulsante + pannello con bottoni", "Il pulsante «Prenota a voce» diventa l'orb; chat «Scrivi» a parte; test su /test-voice"]]
    d.add("Gli ultimi giorni: problema → decisione", table(["Problema", "Decisione"], rows))

    # ---------------------------------------------------------------- 12 pattern
    s = []
    pats = [("File condivisi", "→ conflitti di merge", "un file per ruolo + hash", RED),
            ("Modelli piccoli", "→ errori e frasi tecniche", "il codice decide, filtri", BROWN),
            ("Hardware debole", "→ latenza e RAM", "warm-up, contesto, cache", GOLD),
            ("Dati personali", "→ architettura", "un solo endpoint, anonimizzazione", GREEN),
            ("Docs e config", "→ si disallineano", "test sui docs, doctor", BLUE)]
    for i, (a, b, c, col) in enumerate(pats):
        x = 6 + i * 230
        s.append(box(x, 20, 210, 70, a, fill=col, stroke=col, color="#fff", size=20))
        s.append(text(x + 105, 125, b, 17, "600", "middle", DARK))
        s.append(arrow(x + 105, 138, x + 105, 180))
        s.append(box(x, 184, 210, 90, c, fill="#fff", stroke=col, size=17))
    s.append(text(576, 340, "Sette problemi, cinque cause: ogni decisione di progetto nasce da un incidente reale.", 21, "600", "middle", DARK))
    d.add("Le cinque cause dietro i problemi ricorrenti", svg(1152, 380, "".join(s)))

    # ---------------------------------------------------------------- 13 aperti
    d.add("Cosa resta aperto", '<div class="cols"><div class="col card red"><h2>Rischi e limiti</h2>' + ul([
        "La prova <b>a tre macchine</b> non è ancora stata fatta dal vivo",
        "Il BE scrive data e customer_id in cima al prompt: ogni nuovo cliente fa rileggere tutto al modello",
        "Il BE a volte risponde con testo invece di usare gli strumenti",
        "Il riconoscimento è fissato sulla lingua dell'.env: altre lingue non sono trascritte bene",
        "Nessun endpoint «elenco prenotazioni del cliente»: la pagina ricorda i codici nel browser"]) + '</div>'
        '<div class="col card green"><h2>Prossimi passi</h2>' + ul([
            "Spostare le righe per cliente in fondo al prompt del BE",
            "Allineare il prompt vocale del BE a <code>voice/src/voicebot/prompts.py</code>",
            "Provare il flusso su macchine più potenti e misurare i tempi",
            "Valutare il cognome solo quando c'è una prenotazione simile (serve il BE)",
            "Provare Docker (<code>voice/Dockerfile</code> non è mai stato costruito qui)"]) + "</div></div>")
    return d
