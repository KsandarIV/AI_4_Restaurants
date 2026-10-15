<<<<<<< HEAD
import datetime
from sqlalchemy.orm import Session
from backend.database.models import RestaurantTable, MenuItem, RestaurantInfo, Reservation

def seed_database(db: Session, force: bool = False):
    """
    Seed initial tables, rich menu, restaurant info, and demo reservations.
    If force=True, clears and re-seeds all data.
    """
    if force:
        db.query(Reservation).delete()
        db.query(MenuItem).delete()
        db.query(RestaurantTable).delete()
        db.query(RestaurantInfo).delete()
        db.commit()

    # -------------------------------------------------------------
    # 1. Tavoli del Ristorante (15 Tavoli tra interno, terrazza, giardino)
    # -------------------------------------------------------------
    if db.query(RestaurantTable).count() == 0:
        tables = [
            # Tavoli da 2 persone
            RestaurantTable(table_number=1, capacity=2, location="interno"),
            RestaurantTable(table_number=2, capacity=2, location="interno"),
            RestaurantTable(table_number=3, capacity=2, location="terrazza"),
            RestaurantTable(table_number=4, capacity=2, location="giardino"),

            # Tavoli da 4 persone
            RestaurantTable(table_number=5, capacity=4, location="interno"),
            RestaurantTable(table_number=6, capacity=4, location="interno"),
            RestaurantTable(table_number=7, capacity=4, location="terrazza"),
            RestaurantTable(table_number=8, capacity=4, location="giardino"),

            # Tavoli da 6 persone
            RestaurantTable(table_number=9, capacity=6, location="interno"),
            RestaurantTable(table_number=10, capacity=6, location="terrazza"),
            RestaurantTable(table_number=11, capacity=6, location="giardino"),

            # Tavoli da 8 persone
            RestaurantTable(table_number=12, capacity=8, location="interno"),
            RestaurantTable(table_number=13, capacity=8, location="terrazza"),

            # Tavoli grandi per gruppi (10-12 persone)
            RestaurantTable(table_number=14, capacity=10, location="interno"),
            RestaurantTable(table_number=15, capacity=12, location="giardino"),
        ]
        db.add_all(tables)
        db.commit()

    # -------------------------------------------------------------
    # 2. Menu Completo (Antipasti, Primi, Secondi, Pizze, Contorni, Dessert, Bevande)
    # -------------------------------------------------------------
    if db.query(MenuItem).count() == 0:
        menu_items = [
            # --- ANTIPASTI ---
            MenuItem(
                category="Antipasti",
                name="Bruschette della Tradizione",
                description="Pane casereccio di Gragnano tostato, pomodorini del Piennolo del Vesuvio DOP, aglio, basilico e olio EVO.",
                price=6.50,
                allergens="glutine",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=False
            ),
            MenuItem(
                category="Antipasti",
                name="Tagliere Campano DOP",
                description="Prosciutto crudo di Parma 24 mesi, salame napoletano, provolone del monaco, bocconcini di mozzarella di bufala e confettura di fichi.",
                price=14.50,
                allergens="lattosio",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),
            MenuItem(
                category="Antipasti",
                name="Polpo alla Luciana",
                description="Polpo verace stufato a fuoco lento in coccio con pomodoro San Marzano, olive nere di Gaeta, capperi di Salina e crostini.",
                price=13.50,
                allergens="molluschi, glutine",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Antipasti",
                name="Parmigiana di Melanzane nel Coccio",
                description="Melanzane dorate, sugo ristretto di pomodoro, fior di latte di Agerola e parmigiano reggiano 24 mesi.",
                price=9.50,
                allergens="lattosio, uova",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=True
            ),

            # --- PRIMI PIATTI ---
            MenuItem(
                category="Primi",
                name="Paccheri alla Sorrentina",
                description="Paccheri di Gragnano IGP con passata verace di pomodoro, cubetti di mozzarella filante e basilico al forno.",
                price=12.00,
                allergens="glutine, lattosio",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Primi",
                name="Spaghetti alle Vongole Veraci",
                description="Spaghetti trafilati al bronzo con vongole fresche di Pozzuoli, aglio, prezzemolo fresco e peperoncino dolce.",
                price=16.50,
                allergens="glutine, molluschi",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Primi",
                name="Risotto ai Funghi Porcini del Matese",
                description="Riso Carnaroli mantecato all'onda con funghi porcini freschi, burro d'alpeggio e cialda di parmigiano.",
                price=15.00,
                allergens="lattosio",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=True
            ),
            MenuItem(
                category="Primi",
                name="Gnocchi Gluten-Free al Ragù Napoletano",
                description="Gnocchi di patate senza glutine fatti in casa con tradizionale ragù di carne cotto per 6 ore.",
                price=13.50,
                allergens="",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),

            # --- PIZZE NAPOLETANE ---
            MenuItem(
                category="Pizze",
                name="Pizza Margherita Verace DOP",
                description="Pomodoro San Marzano DOP, mozzarella di bufala campana DOP, basilico fresco e olio extravergine d'oliva.",
                price=8.50,
                allergens="glutine, lattosio",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Pizze",
                name="Pizza Marinara Tradizionale",
                description="Pomodoro San Marzano DOP, aglio a fettine, origano di montagna e olio extravergine (100% Vegana).",
                price=6.50,
                allergens="glutine",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=False
            ),
            MenuItem(
                category="Pizze",
                name="Pizza Diavola Partenopea",
                description="Pomodoro, fior di latte, salame napoletano piccante a fette e peperoncino.",
                price=9.50,
                allergens="glutine, lattosio",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=False
            ),

            # --- SECONDI PIATTI ---
            MenuItem(
                category="Secondi",
                name="Filetto di Orata all'Acqua Pazza",
                description="Filetto di orata freschissima cotta con pomodorini vesuviani, aglio, vino bianco Falanghina e prezzemolo.",
                price=18.50,
                allergens="pesce",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),
            MenuItem(
                category="Secondi",
                name="Tagliata di Manzo Black Angus",
                description="300g di carne cotta alla griglia su pietra lavica, servita con rucola selvatica, pomodorini e scaglie di grana.",
                price=22.00,
                allergens="lattosio",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),
            MenuItem(
                category="Secondi",
                name="Frittura Mista di Paranza",
                description="Calamari, gamberi di nassa e pesciolini di scoglio infarinati e fritti al momento con maionese al limone.",
                price=17.00,
                allergens="glutine, crostacei, molluschi, pesce",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=False
            ),

            # --- CONTORNI ---
            MenuItem(
                category="Contorni",
                name="Friarielli Napoletani Saltati",
                description="Cime di rapa tipiche saltate in padella con aglio, olio EVO e peperoncino.",
                price=5.50,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Contorni",
                name="Patate al Forno Aromatizzate al Rosmarino",
                description="Patate caserecce cotte a legna croccanti fuori e morbide dentro.",
                price=5.00,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Contorni",
                name="Insalata Mista di Stagione",
                description="Misticanza fresca, finocchi, carote e noci tostate con citronette al limone di Sorrento.",
                price=5.00,
                allergens="frutta a guscio",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),

            # --- DESSERT ---
            MenuItem(
                category="Dessert",
                name="Tiramisù Tradizionale della Casa",
                description="Savoiardi sardi, caffè espresso napoletano, crema soffice al mascarpone e cacao amaro fondente.",
                price=6.50,
                allergens="glutine, lattosio, uova",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Dessert",
                name="Babà Napoletano al Rum con Crema e Amarene",
                description="Impasto a lenta lievitazione inzuppato nel rum invecchiato con crema chantilly e amarene sciroppate.",
                price=7.00,
                allergens="glutine, lattosio, uova",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Dessert",
                name="Delizia al Limone di Sorrento",
                description="Pan di spagna soffice farcito e ricoperto con crema profumata ai limoni IGP della Costiera Amalfitana.",
                price=6.50,
                allergens="glutine, lattosio, uova",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Dessert",
                name="Sorbetto al Limone e Zenzero (Senza Lattosio)",
                description="Freschissimo sorbetto artigianale 100% vegetale, senza glutine e senza lattosio.",
                price=5.00,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),

            # --- BEVANDE E VINI ---
            MenuItem(
                category="Bevande",
                name="Acqua Minerale Naturale / Frizzante (0.75L)",
                description="In bottiglia di vetro da sorgente campana.",
                price=2.50,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Bevande",
                name="Calice Falanghina del Sannio DOC",
                description="Vino bianco fresco, minerale e fruttato, perfetto per antipasti e pesce.",
                price=5.50,
                allergens="solfiti",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Bevande",
                name="Calice Aglianico del Taburno DOCG",
                description="Vino rosso corposo, strutturato con sentori di mora e spezie, ideale per carne e primi saporiti.",
                price=6.00,
                allergens="solfiti",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Bevande",
                name="Birra Artigianale Partenopea (0.33L)",
                description="Birra bionda non filtrata a bassa fermentazione, prodotta con malti italiani.",
                price=6.00,
                allergens="glutine",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=False
            ),
            MenuItem(
                category="Bevande",
                name="Caffè Espresso Napoletano",
                description="Miscela arabica e robusta tostata a legna, servito rigorosamente in tazzina bollente.",
                price=1.80,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Bevande",
                name="Limoncello di Sorrento della Casa",
                description="Liquore digestivo naturale fatto a mano con scorze di limone IGP e servito ghiacciato.",
                price=3.50,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            )
        ]
        db.add_all(menu_items)
        db.commit()

    # -------------------------------------------------------------
    # 3. Informazioni sul Ristorante
    # -------------------------------------------------------------
    if db.query(RestaurantInfo).count() == 0:
        info_list = [
            RestaurantInfo(
                key="name",
                value="Trattoria Bella Napoli",
                description="Nome ufficiale dell'insegna"
            ),
            RestaurantInfo(
                key="address",
                value="Via Toledo 142, 80134 Napoli (NA)",
                description="Indirizzo e geolocalizzazione (fermata Metro Toledo a 100 metri)"
            ),
            RestaurantInfo(
                key="phone",
                value="+39 081 555 1234",
                description="Recapito telefonico per urgenze e tavolate numerose"
            ),
            RestaurantInfo(
                key="email",
                value="prenotazioni@trattoriabellanapoli.it",
                description="Contatto email"
            ),
            RestaurantInfo(
                key="opening_hours",
                value="Aperto dal Martedì alla Domenica. Turno pranzo: 12:00 - 15:00 (ultimo arrivo ore 14:00). Turno cena: 19:00 - 23:30 (ultimo arrivo ore 22:00). Lunedì giorno di chiusura settimanale.",
                description="Orari di apertura, turni e ultimo orario utile per ordinare"
            ),
            RestaurantInfo(
                key="parking",
                value="Convenzione attiva con il 'Garage Toledo' a soli 50 metri (tariffa agevolata di 3 euro l'ora per i clienti del ristorante con timbro sul biglietto).",
                description="Indicazioni per il parcheggio auto e moto"
            ),
            RestaurantInfo(
                key="services",
                value="Climatizzazione in tutte le sale, terrazza panoramica e giardino estivo, WiFi ultraveloce gratuito, accesso senza barriere per persone con disabilità, fasciatoi nei bagni e seggioloni per neonati. Cani e animali domestici ammessi.",
                description="Servizi generali, accessibilità e policy animali"
            ),
            RestaurantInfo(
                key="payment_methods",
                value="Contanti, Bancomat, Carte di Credito (Visa, Mastercard, Maestro, American Express), Apple Pay, Google Pay e Satispay.",
                description="Metodi di pagamento elettronici e contanti"
            ),
            RestaurantInfo(
                key="allergens_policy",
                value="La nostra cucina è dotata di un'area separata per la preparazione di piatti senza glutine per celiaci. Il nostro personale è formato su tutte le 14 categorie di allergeni.",
                description="Policy sicurezza alimentare e intolleranze"
            )
        ]
        db.add_all(info_list)
        db.commit()

    # -------------------------------------------------------------
    # 4. Prenotazioni Demo Pre-caricate (utili per test e presentazione)
    # -------------------------------------------------------------
    # Se non ci sono prenotazioni demo, ne creiamo alcune con date future dinamiche
    today = datetime.date.today()
    
    # Calcola date future che non cadano di Lunedì
    def get_valid_future_date(days_ahead: int) -> str:
        d = today + datetime.timedelta(days=days_ahead)
        if d.weekday() == 0:  # Se è Lunedì, sposta al Martedì (+1)
            d += datetime.timedelta(days=1)
        return d.isoformat()

    demo_date_1 = get_valid_future_date(1)  # Domani
    demo_date_2 = get_valid_future_date(2)  # Dopodomani
    demo_date_3 = get_valid_future_date(3)  # Tra 3 giorni

    existing_demo = db.query(Reservation).filter(Reservation.booking_code == "RES-DEMO01").first()
    if not existing_demo:
        demo_reservations = [
            Reservation(
                booking_code="RES-DEMO01",
                customer_id="anon_mario_rossi",
                table_id=5,  # Tavolo 5 (4 persone, interno)
                date=demo_date_1,
                time="20:30",
                shift="cena",
                guests_count=4,
                status="CONFIRMED",
                special_requests="Tavolo tranquillo vicino alla finestra"
            ),
            Reservation(
                booking_code="RES-DEMO02",
                customer_id="anon_lucia_bianchi",
                table_id=3,  # Tavolo 3 (2 persone, terrazza)
                date=demo_date_2,
                time="13:00",
                shift="pranzo",
                guests_count=2,
                status="CONFIRMED",
                special_requests="Festeggiamo anniversario, tavolo appartato"
            ),
            Reservation(
                booking_code="RES-DEMO03",
                customer_id="anon_famiglia_verdi",
                table_id=12, # Tavolo 12 (8 persone, interno)
                date=demo_date_3,
                time="19:30",
                shift="cena",
                guests_count=8,
                status="CONFIRMED",
                special_requests="Necessario un seggiolone per bambino piccolo"
            )
        ]
        db.add_all(demo_reservations)
        db.commit()

if __name__ == "__main__":
    # Permette di eseguire `python -m backend.database.seed_data` per resettare e popolare il DB
    from backend.database.connection import SessionLocal, Base, engine
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session, force=True)
        print("Database riempito con successo con tavoli, menu, info e prenotazioni demo!")
=======
"""Static data of the restaurant: tables, menu, general information.

seed_database fills an empty database; sync_static_data (run at every start) brings the menu and the
information of an EXISTING database in line with this file, so a correction made here reaches everybody.
"""
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.models import RestaurantTable, MenuItem, RestaurantInfo

WEEKDAYS_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

TABLES = [
    (1, 2, "interno"), (2, 2, "interno"), (3, 2, "terrazza"),
    (4, 4, "interno"), (5, 4, "interno"), (6, 4, "terrazza"), (7, 4, "giardino"),
    (8, 6, "interno"), (9, 6, "terrazza"),
    (10, 8, "interno"), (11, 8, "giardino"),
    (12, 10, "interno"),
]


def _dish(category, name, description, price, allergens, vegetarian, vegan, gluten_free, dish_type):
    return dict(category=category, name=name, description=description, price=price, allergens=allergens,
                is_vegetarian=vegetarian, is_vegan=vegan, is_gluten_free=gluten_free, dish_type=dish_type)


MENU_ITEMS = [
    # Antipasti
    _dish("Antipasti", "Bruschette della Tradizione", "Pane casereccio tostato con pomodorini del Piennolo, aglio, olio extravergine e basilico fresco.", 6.50, "glutine", True, True, False, "vegetale"),
    _dish("Antipasti", "Tagliere Campano", "Selezione di salumi nostrani, provolone del monaco, mozzarella di bufala DOP e confettura di fichi.", 14.00, "lattosio", False, False, True, "carne"),
    _dish("Antipasti", "Polpo alla Luciana", "Polpo verace affogato in salsa di pomodoro San Marzano, olive nere di Gaeta e capperi.", 13.50, "molluschi", False, False, True, "pesce"),
    # Primi
    _dish("Primi", "Paccheri alla Sorrentina", "Paccheri di Gragnano con passata di pomodoro, fior di latte filante, parmigiano e basilico al forno.", 12.00, "glutine, lattosio", True, False, False, "vegetale"),
    _dish("Primi", "Spaghetti alle Vongole Veraci", "Spaghetti trafilati al bronzo con vongole fresche, aglio, peperoncino dolce e prezzemolo.", 16.00, "glutine, molluschi", False, False, False, "pesce"),
    _dish("Primi", "Risotto ai Funghi Porcini", "Riso Carnaroli mantecato con funghi porcini dell'Appennino e scaglie di parmigiano reggiano.", 14.50, "lattosio", True, False, True, "vegetale"),
    # Secondi
    _dish("Secondi", "Filetto di Orata all'Acqua Pazza", "Orata fresca locale cotta dolcemente in brodetto di pomodorini, aglio, vino bianco e prezzemolo.", 18.00, "pesce", False, False, True, "pesce"),
    _dish("Secondi", "Tagliata di Manzo al Rosmarino", "300g di manzo italiano cotto alla griglia, servito con rucola selvatica, pomodorini e aceto balsamico.", 21.00, "", False, False, True, "carne"),
    _dish("Secondi", "Parmigiana di Melanzane Classica", "Melanzane fritte, sugo di pomodoro, mozzarella e basilico cotte al coccio.", 11.00, "lattosio, uova", True, False, True, "vegetale"),
    # Contorni
    _dish("Contorni", "Friarielli Saltati in Padella", "Tipici broccoletti napoletani stufati con aglio, olio e peperoncino.", 5.50, "", True, True, True, "vegetale"),
    _dish("Contorni", "Patate al Forno con Rosmarino", "Patate a spicchi dorate e croccanti profumate alle erbe aromatiche.", 5.00, "", True, True, True, "vegetale"),
    # Dessert
    _dish("Dessert", "Tiramisù Artigianale", "Savoiardi bagnati al caffè espresso, crema al mascarpone fresco e cacao amaro.", 6.00, "glutine, lattosio, uova", True, False, False, "dolce"),
    _dish("Dessert", "Babà Napoletano al Rum", "Tradizionale babà lievitato naturalmente e inzuppato al rum con panna fresca montata.", 6.50, "glutine, lattosio, uova", True, False, False, "dolce"),
    _dish("Dessert", "Sorbetto al Limone di Sorrento", "Fresco sorbetto preparato con limoni IGP della costiera amalfitana.", 5.00, "", True, True, True, "dolce"),
    # Bevande
    _dish("Bevande", "Acqua Minerale Naturale / Frizzante (0.75L)", "Acqua in bottiglia di vetro.", 2.50, "", True, True, True, "bevanda"),
    _dish("Bevande", "Calice Falanghina del Sannio DOC", "Vino bianco fresco e minerale ideale con pesce e primi.", 5.50, "solfiti", True, True, True, "bevanda"),
    _dish("Bevande", "Calice Aglianico del Taburno DOCG", "Vino rosso corposo e profumato perfetto per carni e formaggi stagionati.", 6.00, "solfiti", True, True, True, "bevanda"),
    _dish("Bevande", "Caffè Espresso Napoletano", "Miscela arabica tostata secondo tradizione partenopea.", 1.80, "", True, True, True, "bevanda"),
]


def opening_hours_text() -> str:
    """Opening hours written from the settings, so what the bot says is what the booking rules accept."""
    closed = [WEEKDAYS_IT[d] for d in sorted(settings.CLOSED_WEEKDAYS) if 0 <= d <= 6]
    closed_text = f" {' e '.join(closed)}: giorno di chiusura settimanale." if closed else ""
    return (
        f"Pranzo: {settings.LUNCH_START} - {settings.LUNCH_END} (ultimo arrivo alle {settings.LUNCH_LAST_BOOKING}). "
        f"Cena: {settings.DINNER_START} - {settings.DINNER_END} (ultimo arrivo alle {settings.DINNER_LAST_BOOKING})."
        + closed_text
    )


def info_items():
    """(key, value, description) of the general information."""
    return [
        ("name", settings.RESTAURANT_NAME, "Nome ufficiale del ristorante"),
        ("address", "Via Toledo 142, 80134 Napoli (NA)", "Indirizzo e geolocalizzazione"),
        ("phone", "+39 081 555 1234", "Numero di telefono principale per prenotazioni e contatti"),
        ("email", "prenotazioni@trattoriabellanapoli.it", "Email aziendale"),
        ("opening_hours", opening_hours_text(), "Orari di apertura e turni"),
        ("parking", "Disponibile convenzione con il 'Garage Toledo' a 50 metri dal locale (tariffa scontata di €3/ora per i clienti).", "Indicazioni per parcheggio"),
        ("services", "Aria condizionata in tutte le sale, tavoli all'aperto (terrazza e giardino estivo), WiFi gratuito, accesso facilitato per disabili, fasciatoio e seggioloni per bambini. Animali di piccola e media taglia ammessi.", "Servizi offerti, accessibilità e policy animali"),
        ("payment_methods", "Accettiamo contanti, carte di credito (Visa, Mastercard, Maestro, American Express), Bancomat, Apple Pay e Satispay.", "Metodi di pagamento accettati"),
    ]


def seed_database(db: Session):
    """Seed initial tables, menu, and restaurant info if empty."""
    if db.query(RestaurantTable).count() == 0:
        db.add_all([RestaurantTable(table_number=n, capacity=c, location=loc) for n, c, loc in TABLES])
        db.commit()

    if db.query(MenuItem).count() == 0:
        db.add_all([MenuItem(**d) for d in MENU_ITEMS])
        db.commit()

    if db.query(RestaurantInfo).count() == 0:
        db.add_all([RestaurantInfo(key=k, value=v, description=d) for k, v, d in info_items()])
        db.commit()


def sync_static_data(db: Session):
    """Align menu and information of an existing database with this file (insert missing, update changed).

    The sold-out flag (`available`) is left alone: it is managed by the staff. Dishes that exist only in
    the database are never deleted. Run at every start, so it must be idempotent.
    """
    existing = {m.name: m for m in db.query(MenuItem).all()}
    for d in MENU_ITEMS:
        item = existing.get(d["name"])
        if item is None:
            db.add(MenuItem(**d))
            continue
        for field, value in d.items():
            if getattr(item, field) != value:
                setattr(item, field, value)

    info = {i.key: i for i in db.query(RestaurantInfo).all()}
    for key, value, description in info_items():
        row = info.get(key)
        if row is None:
            db.add(RestaurantInfo(key=key, value=value, description=description))
        elif row.value != value or row.description != description:
            row.value, row.description = value, description
    db.commit()
>>>>>>> 17ce76722e00f5178a37172c4e0ab2d0b40cac00
