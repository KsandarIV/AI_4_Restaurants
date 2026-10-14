"""Prove manuali: esegui con  python test_anonimizzatore.py"""
from anonimizzatore import Anonimizzatore

# (frase di input, frase attesa)
CASI = [
    ("Chiamami al 333 1234567", "Chiamami al [TELEFONO_1]"),
    ("Il mio numero è +39 333 123 4567", "Il mio numero è [TELEFONO_1]"),
    ("Tel fisso 02 123456", "Tel fisso [TELEFONO_1]"),
    ("Scrivimi a mario.rossi@gmail.com", "Scrivimi a [EMAIL_1]"),
    ("CF RSSMRA80A01H501U", "CF [CODICE_FISCALE_1]"),
    ("Abito in via Garibaldi 12 a Milano", "Abito in [INDIRIZZO_1] a Milano"),
    ("Sono Mario Rossi, vorrei prenotare per 4", "Sono [NOME_1], vorrei prenotare per 4"),
    ("Prenota a nome Rossi per domani alle 20", "Prenota a nome [NOME_1] per domani alle 20"),
    ("Buonasera, sono Luca, siamo in 3 sabato", "Buonasera, sono [NOME_1], siamo in 3 sabato"),
    ("mi chiamo giulia bianchi e vorrei un tavolo", "mi chiamo [NOME_1] e vorrei un tavolo"),
    ("Il tavolo è per Marco e Sara venerdì sera", "Il tavolo è per [NOME_1] e [NOME_2] venerdì sera"),
    ("Vorrei cambiare la prenotazione di Anna Verdi", "Vorrei cambiare la prenotazione di [NOME_1]"),
    # Cose che NON devono essere toccate:
    ("Tavolo per 4 persone il 12/05/2025 alle 20:30", "Tavolo per 4 persone il 12/05/2025 alle 20:30"),
    ("Prenota per 12 persone", "Prenota per 12 persone"),
    ("Avete la pizza margherita? Siete a Roma?", "Avete la pizza margherita? Siete a Roma?"),
    ("Buonasera, vorrei vedere il menu", "Buonasera, vorrei vedere il menu"),
    ("Sono vegetariano, avete opzioni?", "Sono vegetariano, avete opzioni?"),
]

errori = 0
for ingresso, atteso in CASI:
    ottenuto = Anonimizzatore().anonimizza(ingresso)  # nuovo oggetto: numerazione da 1
    ok = ottenuto == atteso
    errori += not ok
    print("OK " if ok else "KO ", "|", ingresso, "->", ottenuto)
    if not ok:
        print("      atteso:", atteso)

# Stesso valore ripetuto = stesso segnaposto; il ripristino rimette i dati veri.
a = Anonimizzatore()
anon = a.anonimizza("Sono 333 1234567, richiamate il 333 1234567")
assert anon == "Sono [TELEFONO_1], richiamate il [TELEFONO_1]", anon
assert a.ripristina("Vi richiamiamo al [TELEFONO_1]") == "Vi richiamiamo al 333 1234567"

print(f"\n{errori} errori su {len(CASI)}")
