"""Rimozione dei dati personali dal testo prima dell'invio al BE.

Tre livelli, in quest'ordine:
1. regex per dati con forma fissa (email, codice fiscale, telefono, indirizzo);
2. regex su frasi tipiche che introducono un nome ("a nome di Rossi", "mi chiamo ...");
3. modello spaCy locale (NER) come rete di sicurezza per altri nomi di persona.

STATO: il modulo funziona da solo (vedi test_anonimizzatore.py) ma NON è ancora
collegato al chatbot. Le scelte qui sotto dipendono dal BE e vanno concordate:

TODO(BE) 1 - Il BE ha bisogno dei dati veri?
    Ora al BE arriva solo "[NOME_1]", "[TELEFONO_1]", ecc. Se il BE deve salvare
    nel DB il nome o il telefono veri della prenotazione, i segnaposto non bastano.
    Opzioni: (a) il BE salva i segnaposto e il chatbot ricorda a chi corrispondono;
    (b) i dati personali viaggiano in un campo separato dal testo per l'LLM.
    Non ho scelto: va deciso col responsabile del BE (e col vincolo della traccia).
TODO(BE) 2 - Il BE/LLM rispetta i segnaposto?
    ripristina() funziona solo se il BE restituisce i segnaposto IDENTICI
    (es. "[NOME_1]"). Un LLM potrebbe riscriverli ("NOME_1", "il signor [NOME_1]"
    va bene, "nome 1" no). Da provare con il BE vero; forse serve istruire l'LLM.
TODO(BE) 3 - Dati personali nelle risposte del BE
    Se il BE risponde con dati che il chatbot non ha mai inviato (es. l'elenco di
    prenotazioni di un cliente letto dal DB), ripristina() non sa cosa farne.
    Dipende da cosa il BE restituisce.
TODO(BE) 4 - Identificazione della conversazione
    La mappa dei segnaposto vive nell'oggetto Anonimizzatore: serve UNO per
    conversazione (nel chatbot, dentro st.session_state). Se il BE usa un id di
    sessione, vanno collegati. Per modificare/cancellare una prenotazione il BE
    potrebbe chiedere un identificativo (nome? telefono?): cambia cosa si può
    anonimizzare.

DA DECIDERE come gruppo (non dipende dal solo BE):
    - Dati sensibili come allergie o intolleranze ("sono celiaco"): oggi NON
      vengono anonimizzati. Sono dati sulla salute, valutare se oscurarli.
    - Data, ora e numero di persone restano in chiaro (servono al BE).
"""
import re

# L'ORDINE CONTA: l'email va prima del telefono, perché può contenere cifre.
REGOLE = [
    ("EMAIL", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # Codice fiscale: 6 lettere, 2 cifre, 1 lettera, 2 cifre, 1 lettera, 3 cifre, 1 lettera
    ("CODICE_FISCALE", r"\b[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]\b"),
    # Telefono italiano: prefisso +39/0039 facoltativo, poi cellulare (3xx) o fisso (0x...),
    # con spazi, punti o trattini ovunque e prefisso anche tra parentesi: "(333) 1234567", "06 1234 5678".
    # Il testo trovato è solo un candidato: _e_telefono() scarta le date scritte con spazi ("03 11 2026").
    ("TELEFONO", r"(?<![\w/])(?:(?:\+|00)39[\s.-]?)?\(?(?:3\d{2}|0\d{1,3})\)?(?:[\s.-]?\d){5,9}(?![\w/])"),
    # Indirizzo: "via Garibaldi 12", "via Roma, 5", "via Roma n. 5", "piazza San Marco 3b"
    ("INDIRIZZO", r"(?i:\b(?:via|viale|piazza|corso|largo|vicolo)\s+[a-zàèéìòù' .]+?[\s,]+(?:n\.?\s*|civico\s+)?\d{1,4}[a-z]?\b)"),
]

_DATA_SPAZI = re.compile(r"^\d{1,2}[\s.-]\d{1,2}[\s.-](?:19|20)?\d{2}$")
# Via Toledo è la strada del ristorante: se l'utente la nomina sta chiedendo dove siamo, non è casa sua.
INDIRIZZI_DEL_LOCALE = ("toledo",)

# "sono nato il 01/01/1980": si oscura la data, non la frase.
REGOLA_NASCITA = re.compile(
    r"(?i:(\bnat[oa]\s+(?:il|nel|nell'anno)\s+))(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4})"
)

# Frasi che introducono un nome. Il trigger ignora le maiuscole, il nome invece
# deve iniziare con la maiuscola (una o più parole: "Rossi", "Mario Rossi").
_NOME = r"[A-ZÀ-Ý][\w'’-]*(?:\s+[A-ZÀ-Ý][\w'’-]*)*"
REGOLE_NOMI = re.compile(
    r"(?i:\b(?:a nome(?: di)?|mi chiamo|intestata a|intestato a|prenotazione di))\s+(" + _NOME + ")"
)
# "sono" da solo è ambiguo ("Sono Mario" / "Sono Vegetariano"): si anonimizza solo se
# la parola che segue sembra davvero un nome (vedi _sembra_un_nome).
REGOLA_SONO = re.compile(r"(?i:\bsono)\s+(" + _NOME + ")")
# "a nome rossi" scritto tutto in minuscolo: si prende una sola parola, saltando quelle comuni.
REGOLA_NOME_MINUSCOLO = re.compile(
    r"(?i:\b(?:a nome(?: di)?|intestata a|intestato a))\s+([a-zà-ý][\w'’-]*)"
)
NON_NOME_MINUSCOLO = {
    "mio", "mia", "suo", "sua", "loro", "nostro", "nostra", "vostro", "vostra", "del", "della", "dello", "dei",
    "degli", "delle", "un", "una", "uno", "il", "la", "lo", "i", "gli", "le", "me", "te", "lui", "lei", "noi",
    "voi", "tutti", "tutte", "altri", "altre", "mio", "famiglia", "ristorante", "azienda", "società",
    "per", "alle", "alla", "ai", "a", "di", "da", "con", "e", "ok", "grazie", "domani", "stasera", "oggi",
}

# Il modello a volte scambia saluti per nomi: questi non vanno mai anonimizzati.
NON_NOMI = {"buongiorno", "buonasera", "buonanotte", "salve", "ciao", "grazie", "arrivederci"}

# Parole del menu e del locale: il modello le scambia per cognomi ("Babà", "Paccheri alla Sorrentina").
# Un'entità viene ignorata solo se TUTTE le sue parole sono qui: "Margherita Rossi" resta un nome.
PAROLE_DEL_LOCALE = set("""
bruschette tradizione tagliere campano polpo luciana paccheri sorrentina spaghetti vongole veraci risotto
funghi porcini filetto orata acqua pazza tagliata manzo rosmarino parmigiana melanzane classica friarielli
patate tiramisù artigianale babà napoletano sorbetto limone sorrento falanghina sannio aglianico taburno
espresso caffè margherita marinara diavola capricciosa napoli toledo garage bella trattoria
""".split())

_nlp = None  # caricato una sola volta, alla prima richiesta (il caricamento è lento)


def _carica_modello():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("it_core_news_md", disable=["lemmatizer", "parser"])
    return _nlp


def _e_un_telefono(testo):
    """Filtra i candidati della regex: almeno 8 cifre e non una data scritta con spazi ("03 11 2026")."""
    cifre = re.sub(r"\D", "", testo)
    if re.match(r"\s*(?:\+|00)39", testo):
        cifre = re.sub(r"^(?:00)?39", "", cifre)
    return len(cifre) >= 8 and not _DATA_SPAZI.match(testo.strip())


class Anonimizzatore:
    """Sostituisce i dati personali con segnaposto e ricorda la corrispondenza.

    Esempio: "sono Mario Rossi, 333 1234567" -> "sono [NOME_1], [TELEFONO_1]".
    Lo stesso valore riceve sempre lo stesso segnaposto.
    """

    def __init__(self, usa_modello=True):
        self.mappa = {}  # segnaposto -> valore vero, es. {"[TELEFONO_1]": "333 1234567"}
        self.usa_modello = usa_modello

    def anonimizza(self, testo):
        for tipo, regex in REGOLE:
            testo = re.sub(regex, lambda m, t=tipo: self._applica_regola(t, m), testo)
        testo = REGOLA_NASCITA.sub(lambda m: m.group(1) + self._segnaposto("DATA_NASCITA", m.group(2)), testo)
        testo = REGOLE_NOMI.sub(lambda m: self._sostituisci_nome(m), testo)
        testo = REGOLA_SONO.sub(lambda m: self._sostituisci_nome(m) if self._sembra_un_nome(m) else m.group(), testo)
        testo = REGOLA_NOME_MINUSCOLO.sub(
            lambda m: m.group() if m.group(1).lower() in NON_NOME_MINUSCOLO else self._sostituisci_nome(m), testo
        )
        if self.usa_modello:
            testo = self._nomi_con_modello(testo)
        return testo

    def ripristina(self, testo):
        """Rimette i dati veri al posto dei segnaposto (utile per le risposte del BE).

        TODO(BE): non provato con risposte reali del BE, vedi punti 2 e 3 in alto.
        """
        for segnaposto, valore in self.mappa.items():
            testo = testo.replace(segnaposto, valore)
        return testo

    def _applica_regola(self, tipo, m):
        trovato = m.group()
        if tipo == "TELEFONO" and not _e_un_telefono(trovato):
            return trovato
        if tipo == "INDIRIZZO" and any(via in trovato.lower() for via in INDIRIZZI_DEL_LOCALE):
            return trovato
        return self._segnaposto(tipo, trovato)

    def _sostituisci_nome(self, m):
        """Sostituisce solo il gruppo 1 (il nome), lasciando intatta la frase che lo introduce."""
        inizio, fine = m.start(1) - m.start(), m.end(1) - m.start()
        testo = m.group()
        return testo[:inizio] + self._segnaposto("NOME", m.group(1)) + testo[fine:]

    def _sembra_un_nome(self, m):
        """Dopo "sono": "Mario Rossi" è un nome, "Vegetariano" o "Napoletano" no."""
        if m.group(1).lower() in NON_NOMI:
            return False
        if not self.usa_modello:
            return True
        inizio, fine = m.start(1), m.end(1)
        # Si controlla la frase in minuscolo: con la maiuscola il modello scambia per nome
        # qualsiasi parola ("Vegetariano"), in minuscolo distingue meglio nomi e aggettivi.
        doc = _carica_modello()(m.string.lower())
        sovrapposte = [t for t in doc if t.idx < fine and t.idx + len(t) > inizio]
        return any(t.pos_ == "PROPN" for t in sovrapposte) or any(
            e.label_ == "PER" and e.start_char < fine and e.end_char > inizio for e in doc.ents
        )

    def _nomi_con_modello(self, testo):
        entita = [
            e for e in _carica_modello()(testo).ents
            if e.label_ == "PER" and "[" not in e.text and e.text.lower() not in NON_NOMI
            and any(t.pos_ == "PROPN" for t in e)  # "Posso" a inizio frase è un verbo, non un nome
            and not all(p in PAROLE_DEL_LOCALE for p in e.text.lower().split())
        ]
        # I segnaposto si assegnano in ordine di lettura (per numerarli bene)...
        sostituzioni = [(e.start_char, e.end_char, self._segnaposto("NOME", e.text)) for e in entita]
        # ...ma si inseriscono dalla fine, così le posizioni precedenti restano valide.
        for inizio, fine, segnaposto in reversed(sostituzioni):
            testo = testo[:inizio] + segnaposto + testo[fine:]
        return testo

    def _segnaposto(self, tipo, valore):
        for segnaposto, v in self.mappa.items():
            if v == valore:
                return segnaposto
        numero = sum(1 for s in self.mappa if s.startswith(f"[{tipo}_")) + 1
        segnaposto = f"[{tipo}_{numero}]"
        self.mappa[segnaposto] = valore
        return segnaposto
