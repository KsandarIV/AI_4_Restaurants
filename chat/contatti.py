"""Raccolta di nome e telefono dell'utente, dentro la chat, in un unico messaggio.

Due parti, entrambe senza Streamlit e senza rete (quindi testabili da sole):
- estrai_contatti(): legge un messaggio libero e ne ricava nome e telefono;
- Registrazione: il dialogo (chiedi -> riepilogo -> conferma) che gestisce dati
  mancanti, sbagliati o rifiutati. L'LLM non partecipa a questa fase.

I dati vengono mandati solo all'endpoint clienti del BE, mai all'LLM.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import phonenumbers

REGIONE = "IT"  # per i numeri scritti senza prefisso internazionale
MAX_TENTATIVI = 3  # messaggi consecutivi senza nessun dato nuovo, poi si rinuncia

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SALUTI = re.compile(r"\b(?:ciao|salve|buongiorno|buonasera|buon pomeriggio)\b", re.I)
# Le frasi lunghe vanno prima di quelle corte ("a nome di" prima di "nome").
_FRASI_TEL = re.compile(
    r"\b(?:il mio numero di telefono è|il mio numero è|il mio numero|numero di telefono|numero|telefono|cellulare|cell|tel|recapito)\b\.?",
    re.I,
)
_FRASI_NOME = re.compile(
    r"\b(?:mi chiamo|il mio nome è|il mio nome|nome e cognome|a nome di|a nome|nome|cognome|sono)\b", re.I
)
# Formule di cortesia: non sono né un nome né una domanda ("Mario Rossi, 333 1234567, grazie").
_CORTESIA = re.compile(r"\b(?:grazie(?: mille)?|per favore|per cortesia|prego|cordiali saluti|a presto)\b", re.I)
# Simboli che non compaiono in un nome: segno di codice, HTML o tentativi di iniezione.
_SIMBOLI_SOSPETTI = re.compile(r"[<>{}\[\];=\\|`$]|--")
# Solo congiunzioni: articoli come "la" o "di" possono far parte di un cognome (La Rosa, Di Maio).
_CONGIUNZIONI = re.compile(r"\b(?:e|è|ed|o|oppure)\b", re.I)
_RIFIUTO = re.compile(
    r"\b(?:non voglio|preferisco non|non intendo|non posso dare|no grazie|privacy|perch[eé] (?:servono|devo|dovrei))\b", re.I
)
# Parole che indicano una domanda o una frase, non un nome.
_NON_NOMI = {
    "vorrei", "voglio", "vorremmo", "prenotare", "prenotazione", "tavolo", "menu", "avete", "siete",
    "quanto", "quando", "dove", "come", "perché", "perche", "cosa", "che", "per", "con", "non",
    "grazie", "persone", "orario", "domani", "oggi", "stasera", "posso", "potete", "informazioni",
    "aiuto", "privacy", "si", "sì", "no", "ok",
    "boh", "mah", "uffa", "ehm", "hmm", "ma", "anzi", "però", "pero", "aspetta", "sbagliato", "corretto",
}


@dataclass
class Contatti:
    nome: Optional[str] = None
    telefono: Optional[str] = None  # formato E.164, es. "+393331234567"
    # Possibili: rifiuto, altro, telefono_non_valido, telefoni_multipli, nome_non_chiaro
    problemi: List[str] = field(default_factory=list)


def mostra_telefono(e164):
    """'+393331234567' -> '+39 333 1234567' (per mostrarlo all'utente)."""
    return phonenumbers.format_number(phonenumbers.parse(e164), phonenumbers.PhoneNumberFormat.INTERNATIONAL)


def _formatta_nome(token):
    return token.title() if token.islower() or token.isupper() else token


def estrai_contatti(testo):
    """Ricava nome e telefono da un messaggio scritto liberamente."""
    risultato = Contatti()
    resto = testo.strip()

    # --- Telefono: lo cerca e lo valida la libreria phonenumbers ---
    trovati = {}  # E.164 -> (inizio, fine)
    for m in phonenumbers.PhoneNumberMatcher(resto, REGIONE):
        trovati[phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)] = (m.start, m.end)
    for inizio, fine in sorted(trovati.values(), reverse=True):  # dalla fine, per non spostare le posizioni
        resto = resto[:inizio] + " " + resto[fine:]
    if len(trovati) == 1:
        risultato.telefono = next(iter(trovati))
    elif len(trovati) > 1:
        risultato.problemi.append("telefoni_multipli")
    elif re.search(r"\+?\d[\d\s.\-()/]{2,}\d", resto):  # c'è un tentativo di numero, ma non valido
        risultato.problemi.append("telefono_non_valido")

    # --- Nome: quello che resta togliendo telefono, email e frasi di contorno ---
    resto = _EMAIL.sub(" ", resto)
    resto = re.sub(r"\d+", " ", resto)
    for regola in (_SALUTI, _CORTESIA, _FRASI_TEL, _FRASI_NOME, _CONGIUNZIONI):
        resto = regola.sub(" ", resto)
    parole = re.findall(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", resto)  # lettere, con apostrofi e trattini interni
    parole = [p for p in parole if len(p) > 1]  # le iniziali ("M.") si scartano

    if parole:
        if _SIMBOLI_SOSPETTI.search(testo):
            risultato.problemi.append("nome_non_chiaro")
        elif "?" in testo or {p.lower() for p in parole} & _NON_NOMI:
            risultato.problemi.append("altro")
        elif len(parole) > 5:  # "Maria Grazia De Luca Esposito" sono 5 parole e sono un nome vero
            risultato.problemi.append("nome_non_chiaro")
        else:
            risultato.nome = " ".join(_formatta_nome(p) for p in parole)

    if not risultato.nome and not risultato.telefono and _RIFIUTO.search(testo):
        risultato.problemi = ["rifiuto"]  # "Non voglio..." contiene "non", ma è un rifiuto e non una domanda
    return risultato


MESSAGGIO_INIZIALE = (
    "Benvenuto! Per gestire le prenotazioni mi servono il suo nome e cognome e un numero di telefono. "
    "Può scriverli insieme in un unico messaggio? Per esempio: Mario Rossi, 333 1234567. "
    "Li usiamo solo per gestire la sua prenotazione."
)
_ESEMPIO = "Mi servono il suo nome e cognome e un numero di telefono, in un unico messaggio. Esempio: Mario Rossi, 333 1234567."
_FRASI_PROBLEMI = {
    "rifiuto": "Capisco la preoccupazione: nome e telefono servono solo per confermare la prenotazione o avvisarla in caso di imprevisti.",
    "altro": "Prima di tutto mi servono i suoi dati di contatto, poi potrà chiedermi tutto quello che vuole.",
    "telefono_non_valido": "Il numero di telefono non sembra valido (esempi: 333 1234567 oppure +39 02 1234567).",
    "telefoni_multipli": "Ho trovato più numeri di telefono: quale devo usare per la prenotazione?",
    "nome_non_chiaro": "Non sono sicuro di aver capito il nome: può scrivermi nome e cognome?",
}
_PAROLE_SI = r"(?:s[ìi]|ok|certo|corretto|esatto|esattamente|giusto|perfetto|confermo|va bene|assolutamente|yes)"
# Un "sì" vale solo se è TUTTO il messaggio ("sì", "sì, grazie", "ok perfetto"): con "sì ma il numero è sbagliato"
# non si registra niente. _INIZIA_CON_SI serve a riconoscere le risposte miste, per chiedere chiarimenti.
_SI = re.compile(
    rf"^\W*{_PAROLE_SI}(?:[\W]+(?:{_PAROLE_SI}|grazie|tutto (?:ok|giusto|corretto)|[èe] corretto))*\W*$", re.I
)
_INIZIA_CON_SI = re.compile(rf"^\W*{_PAROLE_SI}\b", re.I)
_NO = re.compile(r"^\W*(?:no|sbagliato|errato|non è corretto|non e corretto)\b", re.I)


class Registrazione:
    """Dialogo di registrazione. Fasi: raccolta -> conferma -> completata | rinunciata.

    gestisci(testo) restituisce (risposta, azione). L'azione dice cosa deve fare l'app:
    "registra" = inviare nome e telefono al BE; "rinuncia" = proseguire senza registrazione.
    """

    def __init__(self):
        self.fase = "raccolta"
        self.nome = None
        self.telefono = None
        self.tentativi = 0

    def gestisci(self, testo) -> Tuple[str, Optional[str]]:
        return self._conferma(testo) if self.fase == "conferma" else self._raccogli(testo)

    def _raccogli(self, testo):
        contatti = estrai_contatti(testo)
        progresso = self._aggiorna(contatti, testo)
        if self.nome and self.telefono:
            self.fase = "conferma"
            return self._riepilogo(), None
        if not progresso:
            self.tentativi += 1
            if self.tentativi >= MAX_TENTATIVI:
                self.fase = "rinunciata"
                return (
                    "Senza questi dati non posso gestire le prenotazioni, ma posso comunque rispondere a domande "
                    "su menu, orari e informazioni sul locale. Come posso aiutarla?",
                    "rinuncia",
                )
        return self._richiesta_mancanti(contatti.problemi), None

    def _conferma(self, testo):
        if _SI.match(testo):
            self.fase = "completata"
            return f"Perfetto, grazie {self.nome}! Registro i suoi dati.", "registra"
        contatti = estrai_contatti(testo)
        # Una risposta che comincia con sì/no ma contiene altro è una correzione solo se porta un
        # telefono o dice "mi chiamo...": altrimenti le parole sparse ("il numero è sbagliato") non sono dati.
        risposta_mista = _NO.match(testo) or _INIZIA_CON_SI.match(testo)
        porta_un_dato = contatti.telefono or _FRASI_NOME.search(testo)
        if not (risposta_mista and not porta_un_dato) and self._aggiorna(contatti, testo):
            return self._riepilogo(), None
        if _NO.match(testo):
            self.nome = self.telefono = None
            self.fase = "raccolta"
            return "Nessun problema, ricominciamo. " + _ESEMPIO, None
        return "Non ho capito: i dati sono corretti? Risponda sì o no.", None

    def _aggiorna(self, contatti, testo):
        """Salva i dati nuovi o corretti. Restituisce True se è cambiato qualcosa.

        Se un nome è già stato registrato, una parola sola ("mah", "boh") non lo sostituisce:
        serve un nome di almeno due parole, o un "no" / "mi chiamo" esplicito.
        """
        cambiato = False
        nome = contatti.nome
        if nome and self.nome and nome != self.nome:
            if len(nome.split()) < 2 and not (_NO.match(testo) or _FRASI_NOME.search(testo)):
                nome = None
        if nome and nome != self.nome:
            self.nome, cambiato = nome, True
        if contatti.telefono and contatti.telefono != self.telefono:
            self.telefono, cambiato = contatti.telefono, True
        return cambiato

    def _riepilogo(self):
        return f"Ho capito: {self.nome}, {mostra_telefono(self.telefono)}. È corretto? (sì/no)"

    def _richiesta_mancanti(self, problemi):
        righe = [_FRASI_PROBLEMI[p] for p in problemi if p in _FRASI_PROBLEMI]
        if self.nome and not self.telefono:
            righe.append(f"Grazie {self.nome}! Mi manca solo il numero di telefono.")
        elif self.telefono and not self.nome:
            righe.append(f"Ho il numero {mostra_telefono(self.telefono)}. Mi manca solo il nome.")
        else:
            righe.append(_ESEMPIO)
        return " ".join(righe)
