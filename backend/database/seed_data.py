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
