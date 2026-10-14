"""Prove manuali: esegui con  python test_contatti.py"""
import sys

from contatti import Registrazione, estrai_contatti

TEL = "+393331234567"

# (messaggio, nome atteso, telefono atteso, problemi attesi)
CASI = [
    # --- messaggi corretti, in vari modi ---
    ("Mario Rossi, 333 1234567", "Mario Rossi", TEL, []),
    ("Sono Mario Rossi e il mio numero è 333 1234567", "Mario Rossi", TEL, []),
    ("mi chiamo mario rossi, tel 333.123.4567", "Mario Rossi", TEL, []),
    ("333 1234567 Mario Rossi", "Mario Rossi", TEL, []),
    ("Buonasera, sono Luca Bianchi +39 333 1234567", "Luca Bianchi", TEL, []),
    ("Giulia De Luca 3331234567", "Giulia De Luca", TEL, []),
    ("Anna D'Angelo, cellulare: 333-1234567", "Anna D'Angelo", TEL, []),
    ("Rossi 333 1234567", "Rossi", TEL, []),                      # un solo nome basta
    ("Marco La Rosa, 02 1234567", "Marco La Rosa", "+39021234567", []),  # fisso; "La" resta nel cognome
    ("Mario Rossi, +44 20 7946 0958", "Mario Rossi", "+442079460958", []),  # numero estero
    # --- dati mancanti ---
    ("Mario Rossi", "Mario Rossi", None, []),
    ("333 1234567", None, TEL, []),
    ("", None, None, []),
    ("ciao", None, None, []),
    # --- dati sbagliati ---
    ("Mario Rossi, 333 12", "Mario Rossi", None, ["telefono_non_valido"]),
    ("Mario Rossi, 12345", "Mario Rossi", None, ["telefono_non_valido"]),
    ("Mario Rossi, 333 1234567 oppure 340 7654321", "Mario Rossi", None, ["telefoni_multipli"]),
    ("Sono un cliente che vorrebbe prenotare un tavolo per tanta gente", None, None, ["altro"]),
    ("Maria Grazia Anna Teresa Rossi Bianchi", None, None, ["nome_non_chiaro"]),
    # --- altro ---
    ("Avete la pizza?", None, None, ["altro"]),
    ("Vorrei prenotare per 4 persone", None, None, ["altro"]),
    ("Non voglio dare i miei dati", None, None, ["rifiuto"]),
    ("Preferisco non dirlo, grazie", None, None, ["rifiuto"]),
]

errori = 0
for testo, nome, tel, problemi in CASI:
    c = estrai_contatti(testo)
    ok = (c.nome, c.telefono, c.problemi) == (nome, tel, problemi)
    errori += not ok
    print("OK " if ok else "KO ", "|", repr(testo), "->", (c.nome, c.telefono, c.problemi))
    if not ok:
        print("      atteso:", (nome, tel, problemi))


def dialogo(titolo, scambi, azione_finale, fase_finale):
    """scambi = [(messaggio utente, testo che la risposta deve contenere)]"""
    global errori
    r, azione = Registrazione(), None
    for utente, contiene in scambi:
        risposta, azione = r.gestisci(utente)
        ok = contiene in risposta
        errori += not ok
        print("OK " if ok else "KO ", "|", titolo, "|", repr(utente), "->", risposta)
        if not ok:
            print("      doveva contenere:", repr(contiene))
    ok = azione == azione_finale and r.fase == fase_finale
    errori += not ok
    print("OK " if ok else "KO ", "|", titolo, "| fine:", (azione, r.fase), "atteso:", (azione_finale, fase_finale))
    return r


print()
r = dialogo("tutto giusto", [("Mario Rossi, 333 1234567", "È corretto"), ("sì", "Perfetto")], "registra", "completata")
assert (r.nome, r.telefono) == ("Mario Rossi", TEL)

dialogo("manca il telefono", [
    ("Mario Rossi", "Mi manca solo il numero"),
    ("333 1234567", "È corretto"),
    ("Sì, grazie", "Perfetto"),
], "registra", "completata")

dialogo("telefono sbagliato poi giusto", [
    ("Mario Rossi, 333 12", "non sembra valido"),
    ("333 1234567", "È corretto"),
    ("ok", "Perfetto"),
], "registra", "completata")

dialogo("correzione dopo il riepilogo", [
    ("Mario Rossi, 333 1234567", "È corretto"),
    ("no, il numero è 340 7654321", "340 765 4321"),
    ("sì", "Perfetto"),
], "registra", "completata")

dialogo("'no' e ricomincia", [
    ("Mario Rossi, 333 1234567", "È corretto"),
    ("no", "ricominciamo"),
    ("Luca Verdi, 333 7654321", "Luca Verdi"),
    ("sì", "Perfetto"),
], "registra", "completata")

dialogo("conferma con altre parole", [
    ("Mario Rossi, 333 1234567", "È corretto"),
    ("perfetto, grazie", "Perfetto"),
], "registra", "completata")

r = dialogo("una parola sola non cambia il nome già registrato", [
    ("Mario Rossi, 333 1234567", "È corretto"),
    ("boh", "sì o no"),
], None, "conferma")
assert r.nome == "Mario Rossi"

dialogo("risposta incomprensibile al riepilogo", [
    ("Mario Rossi, 333 1234567", "È corretto"),
    ("mah", "sì o no"),
    ("sì", "Perfetto"),
], "registra", "completata")

dialogo("tre messaggi inutili: si rinuncia", [
    ("Avete la pizza?", "Prima di tutto"),
    ("Quanto costa il menu?", "Prima di tutto"),
    ("Non voglio dare i miei dati", "Senza questi dati"),
], "rinuncia", "rinunciata")

# i messaggi con dati parziali contano come progresso: non si rinuncia
dialogo("il progresso non conta come tentativo fallito", [
    ("Avete la pizza?", "Prima di tutto"),
    ("Mario Rossi", "Mi manca solo il numero"),
    ("boh", "Grazie Mario Rossi"),
    ("333 1234567", "È corretto"),
], None, "conferma")

print(f"\n{errori} errori")
sys.exit(1 if errori else 0)
