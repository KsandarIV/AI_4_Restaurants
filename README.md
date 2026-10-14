# AI 4 Restaurants

Sistema AI per la prenotazione di un tavolo in un ristorante.
Progetto di gruppo (3 persone), ognuna responsabile di un componente.

| Componente | Descrizione |
|---|---|
| **BE** | Backend Python con LLM locale e database SQLite (disponibilità e prenotazioni) |
| **CHAT** | Chatbot testuale che chiama il BE via rete |
| **VOICE** | Voice-bot che chiama il BE via rete |

```
CHAT  --rete LAN-->  BE (Python + LLM + SQLite)  <--rete LAN--  VOICE
```

## Vincoli principali

- I tre componenti girano su **macchine diverse** e comunicano **solo via rete**.
- CHAT e VOICE **rimuovono i dati personali** prima di inviare i messaggi al BE.
- Tutti i modelli girano in **locale**.

## Setup dell'ambiente

Tutti i membri del gruppo usano la **stessa versione di Python (3.11)**.

### 1. Creare l'ambiente conda

```bash
conda create -n chatbot_ristorante python=3.11
conda activate chatbot_ristorante
```

### 2. Installare le librerie

Librerie comuni a tutti:

```bash
pip install requests python-dotenv pytest
```

Poi quelle del proprio componente.

**CHAT**

```bash
pip install streamlit spacy
python -m spacy download it_core_news_sm
```

**BE** (da confermare con chi lo sviluppa)

```bash
pip install fastapi uvicorn ollama
```

**VOICE** (da confermare con chi lo sviluppa)

```bash
pip install faster-whisper
```

Per la sintesi vocale e l'audio da microfono le librerie sono ancora da scegliere.

### 3. Congelare le versioni

Dopo aver verificato che tutto funziona, ognuno esporta le versioni esatte nel
proprio file e lo aggiunge al repository:

```bash
pip freeze > requirements_chat.txt
```

(usare `requirements_be.txt` e `requirements_voice.txt` per gli altri componenti).

Per ricreare l'ambiente da zero:

```bash
conda create -n chatbot_ristorante python=3.11
conda activate chatbot_ristorante
pip install -r requirements_chat.txt
```

## Da decidere insieme

- [ ] Motore dell'LLM locale (es. Ollama) e modello da usare
- [ ] Indirizzo IP e porta del BE nella LAN
- [ ] Endpoint e formato JSON di richiesta e risposta
- [ ] Come identificare una conversazione (id di sessione)
- [ ] Se il BE accetta segnaposto al posto dei dati personali (es. `[NOME_1]`)
