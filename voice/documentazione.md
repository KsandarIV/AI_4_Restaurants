# Voice-bot — Documentazione tecnica (Traccia 3, membro VOICE)

> Leggila anche su server avviato: `http://localhost:8003/tech` (versione stampabile in PDF).
> Stato: allineato al BE reale (`backend/api/routes.py`) e al setup condiviso (`setup/`).

## 1. Cosa fa e vincoli di traccia

Voice-bot per prenotazione/modifica/cancellazione tavolo, consultazione menu e info
ristorante, via voce. Vincoli rispettati:

| # | Vincolo | Come |
|---|---|---|
| 1 | 3 macchine diverse | Voice è un servizio autonomo; al BE parla solo via `BACKEND_BASE_URL` (LAN) |
| 2 | Comunicazione via rete | Solo HTTP/SSE + WebSocket; **zero import** di codice BE/CHAT in `voice/` |
| 3 | PII rimosse prima dell'invio | `pii.scrub_pii` su ogni messaggio (`[EMAIL]`, `[TELEFONO]`, `[CODICE_FISCALE]`, `[CARTA]`) |
| 4 | Modelli 100% locali | faster-whisper, Piper, VAD, Ollama/`gemma4:12b` — nessun provider cloud nel codice |

## 2. Architettura di rete

```
 mic/browser (macchina VOICE o cliente)
   │ WebSocket PCM16LE 16 kHz  (ws://<IP-VOICE>:8003/ws/voice)
   ▼
 VOICE :8003  (VAD → STT → orchestratore → TTS)
   │ HTTP/SSE verso BE (POST /api/chat/stream, GET /api/menu|info|availability, CRUD /api/reservations)
   ▼
 BE :8000  (LangGraph + Ollama gemma4:12b + SQLite) — macchina separata in LAN
```

Perché GitHub condiviso se poi si parla via HTTP: la repo dà a tutti lo stesso
**contratto** (endpoint reali), gli **stub** per test offline e il **setup unico**
(`setup/` → un solo `.venv`). A runtime ogni componente usa solo la sua cartella.

## 3. Flusso audio (core loop, `pipeline/session.py`)

Producer-Consumer su `asyncio.Queue` bounded (backpressure, niente crescita memoria):

```
WS-reader ──bytes PCM──▶ audio_in_q ──▶ VAD ──segmenti──▶ segment_q
 ──▶ STT (timeout 30s) ──testo──▶ text_q ──▶ LLM: pump_tokens ──token──▶ token_q
 ──▶ TTS (sintesi per-frase) ──audio──▶ audio_out_q ──▶ WS-writer
```

- **Streaming reale**: i token LLM alimentano il TTS mentre arrivano; l'audio parte
  prima della fine del turno. (Nota onesta: il BE fa inferenza completa e poi
  streamma parola-a-parola a 30 ms — il primo token costa un turno intero.)
- **Barge-in**: se il VAD sente voce mentre `speaking_event` è attivo, il contatore
  di generazione invalida il turno, svuota `audio_out_q`, resetta VAD e invia
  `{"event": "barge_in"}` al client.
- **Shutdown**: `close()` manda poison-pill, cancella i task con timeout 5 s, chiude STT/TTS.

## 4. Moduli e interfacce (`interfaces.py`)

`AbstractVAD` → `EnergyVAD` (default, zero-dep) / `WebRtcVADWrapper` (opzionale, richiede
compilatore C++: il setup lo salta senza bloccare). `AbstractSTT` → `FasterWhisperSTT`
locale + `FakeSTT`. `AbstractTTS` → `PiperTTS` streaming per-frase + `FakeTTS`.
`AbstractLLMOrchestrator` → `BackendOrchestrator`: history trim, shortcut diretti
menu/info/disponibilità, `session_id`+`customer_id` anonimo stabili per la memoria LangGraph.

## 5. Modelli locali e dipendenze

| Uso | Modello | Dove |
|---|---|---|
| LLM dialogo | `gemma4:12b` via Ollama | macchina BE (`ollama pull gemma4:12b` dallo setup) |
| STT it | faster-whisper `tiny` (configurabile) | macchina VOICE, download auto al primo uso |
| TTS it | Piper `it_IT-riccardo-x_low` | `voice/models/` (setup lo scarica) |
| VAD | Energy (default) / webrtc | macchina VOICE |
| NER PII (chat) | `it_core_news_md` | macchina CHAT |

Dipendenze unificate in `setup/requirements.txt` (fonte di verità; `voice/pyproject.toml`
la rispecchia per l'editable install). `.env` unico in root (`.env.example`).

## 6. Contratto BE usato

`GET /health|/api/health`, `POST /api/chat/stream` (SSE `{"token"}`…`[DONE]`),
`GET /api/availability`, `POST|GET|PATCH|PUT|DELETE /api/reservations[/{booking_code}]`,
`GET /api/menu`, `GET /api/info`. Codici prenotazione formato `RES-xxxx`.

## 7. Test — due modalità

- **Offline** (`pytest tests`, 13 test): stub BE locale (`tests/stub_be.py`, contratto
  completo) + VERO `BackendClient`/orchestratore; pipeline con STT/TTS fake; PII-scrub verificato.
- **LAN**: stub sostituito dal BE vero cambiando solo `BACKEND_BASE_URL`.

## 8. Checklist test incrociati — cosa chiedere ai colleghi

**Al collega BE (serve la sua macchina):**
1. IP LAN + conferma ascolto su `0.0.0.0:8000` (non `localhost`, altrimenti è irraggiungibile).
2. `ollama serve` attivo, `ollama list` mostra `gemma4:12b`.
3. Firewall Windows: **porta 8000 in ingresso** aperta.
4. DB seedato (tavoli/menu/info) + 1 **codice prenotazione di test** esistente (es. per provare modifica/cancellazione via voce).
5. Orari/slot reali (pranzo/cena, chiusura lunedì) per validare le risposte vocali.
6. Prova fumo dalla tua macchina: `GET http://<IP-BE>:8000/api/health` e
   `python client_demo.py http://<IP-BE>:8000` prima di accendere Voice.

**Al collega CHAT (coerenza, non connessione — chat e voice NON si parlano):**
7. Allineare le frasi di anonimizzazione (il suo `anonimizzatore.py` usa `[NOME_1]`,
   voice usa `[EMAIL]`…: decidere un formato unico se il BE deve citarli).
8. Stesso `customer_id` anonimo per sessione? Oggi voice lo genera da solo.
9. Condividere gli script di test LAN usati, per pari condizioni.

**Sulla tua macchina:** firewall **8003 in ingresso** aperto; `BACKEND_BASE_URL=http://<IP-BE>:8000`
nel `.env`; `STT/TTS_BACKEND=fake` solo per debug senza modelli.

## 9. Punti di forza e punti deboli (onesti, per il cliente)

**Forza:** latenza percepita bassa (TTS in overlap allo stream); interruzione naturale
(barge-in); resilienza (retry/backoff BE, code bounded, setup auto-riparante);
privacy-by-design (PII mai inviate); 100% on-premise (niente costi API, dati in casa);
testabile senza rete.

**Deboli / rischi:** primo token lento (inferenza BE completa prima dello stream —
mitigabile con shortcut tool e cache risposte frequenti); STT `tiny` sacrifica
accuratezza per CPU (upgrade a `small`/`medium` con GPU); diarizzazione assente
(una voce alla volta); nessuna autenticazione su WS/BE (ok in LAN demo, da aggiungere
— token — per produzione); accenti/rumore degradano VAD energetico (passare a webrtc
con Build Tools installati).

## 10. Avvio demo (dalla root)

```bat
python setup\setup_env.py
copy .env.example .env        & REM imposta BACKEND_BASE_URL
.venv\Scripts\python -m voicebot
REM WS: ws://localhost:8003/ws/voice | Tech page: http://localhost:8003/tech
REM Prova vocale (mic, solo localhost): http://localhost:8003/prova-vocale
REM Voce da QUALUNQUE pc (mic locale, niente browser): .venv\Scripts\python -m voicebot.v2
```
