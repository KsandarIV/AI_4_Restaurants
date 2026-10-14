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
    # Telefono italiano: prefisso +39/0039 facoltativo, poi cellulare (3xx) o fisso (0x...).
    # Le date (es. 12/05/2025) non vengono toccate: hanno "/" e non iniziano con 3xx o 0x.
    ("TELEFONO", r"(?<![\w/])(?:(?:\+|00)39[\s.-]?)?(?:3\d{2}|0\d{1,3})[\s.-]?\d{3}[\s.-]?\d{3,4}(?![\w/])"),
    # Indirizzo: "via Garibaldi 12", "piazza San Marco 3b"
    ("INDIRIZZO", r"(?i:\b(?:via|viale|piazza|corso|largo|vicolo)\s+[a-zàèéìòù' .]+?\s+\d{1,4}[a-z]?\b)"),
]

# Frasi che introducono un nome. Il trigger ignora le maiuscole, il nome invece
# deve iniziare con la maiuscola (una o più parole: "Rossi", "Mario Rossi").
_NOME = r"[A-ZÀ-Ý][\w'’-]*(?:\s+[A-ZÀ-Ý][\w'’-]*)*"
REGOLE_NOMI = re.compile(
    r"(?i:\b(?:a nome(?: di)?|mi chiamo|sono|intestata a|intestato a|prenotazione di))\s+(" + _NOME + ")"
)

# Il modello a volte scambia saluti per nomi: questi non vanno mai anonimizzati.
NON_NOMI = {"buongiorno", "buonasera", "buonanotte", "salve", "ciao", "grazie", "arrivederci"}

_nlp = None  # caricato una sola volta, alla prima richiesta (il caricamento è lento)


def _carica_modello():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("it_core_news_md", disable=["lemmatizer", "parser"])
    return _nlp


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
            testo = re.sub(regex, lambda m: self._segnaposto(tipo, m.group()), testo)
        testo = REGOLE_NOMI.sub(lambda m: m.group().replace(m.group(1), self._segnaposto("NOME", m.group(1))), testo)
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

    def _nomi_con_modello(self, testo):
        entita = [
            e for e in _carica_modello()(testo).ents
            if e.label_ == "PER" and "[" not in e.text and e.text.lower() not in NON_NOMI
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
