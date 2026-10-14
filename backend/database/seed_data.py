from sqlalchemy.orm import Session
from backend.database.models import RestaurantTable, MenuItem, RestaurantInfo

def seed_database(db: Session):
    """Seed initial tables, menu, and restaurant info if empty."""

    # 1. Seed Tables
    if db.query(RestaurantTable).count() == 0:
        tables = [
            RestaurantTable(table_number=1, capacity=2, location="interno"),
            RestaurantTable(table_number=2, capacity=2, location="interno"),
            RestaurantTable(table_number=3, capacity=2, location="terrazza"),
            RestaurantTable(table_number=4, capacity=4, location="interno"),
            RestaurantTable(table_number=5, capacity=4, location="interno"),
            RestaurantTable(table_number=6, capacity=4, location="terrazza"),
            RestaurantTable(table_number=7, capacity=4, location="giardino"),
            RestaurantTable(table_number=8, capacity=6, location="interno"),
            RestaurantTable(table_number=9, capacity=6, location="terrazza"),
            RestaurantTable(table_number=10, capacity=8, location="interno"),
            RestaurantTable(table_number=11, capacity=8, location="giardino"),
            RestaurantTable(table_number=12, capacity=10, location="interno"),
        ]
        db.add_all(tables)
        db.commit()

    # 2. Seed Menu Items
    if db.query(MenuItem).count() == 0:
        menu_items = [
            # Antipasti
            MenuItem(
                category="Antipasti",
                name="Bruschette della Tradizione",
                description="Pane casereccio tostato con pomodorini del Piennolo, aglio, olio extravergine e basilico fresco.",
                price=6.50,
                allergens="glutine",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=False
            ),
            MenuItem(
                category="Antipasti",
                name="Tagliere Campano",
                description="Selezione di salumi nostrani, provolone del monaco, mozzarella di bufala DOP e confettura di fichi.",
                price=14.00,
                allergens="lattosio",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),
            MenuItem(
                category="Antipasti",
                name="Polpo alla Luciana",
                description="Polpo verace affogato in salsa di pomodoro San Marzano, olive nere di Gaeta e capperi.",
                price=13.50,
                allergens="molluschi",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),

            # Primi
            MenuItem(
                category="Primi",
                name="Paccheri alla Sorrentina",
                description="Paccheri di Gragnano con passata di pomodoro, fior di latte filante, parmigiano e basilico al forno.",
                price=12.00,
                allergens="glutine, lattosio",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Primi",
                name="Spaghetti alle Vongole Veraci",
                description="Spaghetti trafilati al bronzo con vongole fresche, aglio, peperoncino dolce e prezzemolo.",
                price=16.00,
                allergens="glutine, molluschi",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Primi",
                name="Risotto ai Funghi Porcini",
                description="Riso Carnaroli mantecato con funghi porcini dell'Appennino e scaglie di parmigiano reggiano.",
                price=14.50,
                allergens="lattosio",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=True
            ),

            # Secondi
            MenuItem(
                category="Secondi",
                name="Filetto di Orata all'Acqua Pazza",
                description="Orata fresca locale cotta dolcemente in brodetto di pomodorini, aglio, vino bianco e prezzemolo.",
                price=18.00,
                allergens="pesce",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),
            MenuItem(
                category="Secondi",
                name="Tagliata di Manzo al Rosmarino",
                description="300g di manzo italiano cotto alla griglia, servito con rucola selvatica, pomodorini e aceto balsamico.",
                price=21.00,
                allergens="",
                is_vegetarian=False,
                is_vegan=False,
                is_gluten_free=True
            ),
            MenuItem(
                category="Secondi",
                name="Parmigiana di Melanzane Classica",
                description="Melanzane fritte, sugo di pomodoro, mozzarella e basilico cotte al coccio.",
                price=11.00,
                allergens="lattosio, uova",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=True
            ),

            # Contorni
            MenuItem(
                category="Contorni",
                name="Friarielli Saltati in Padella",
                description="Tipici broccoletti napoletani stufati con aglio, olio e peperoncino.",
                price=5.50,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Contorni",
                name="Patate al Forno con Rosmarino",
                description="Patate a spicchi dorate e croccanti profumate alle erbe aromatiche.",
                price=5.00,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),

            # Dessert
            MenuItem(
                category="Dessert",
                name="Tiramisù Artigianale",
                description="Savoiardi bagnati al caffè espresso, crema al mascarpone fresco e cacao amaro.",
                price=6.00,
                allergens="glutine, lattosio, uova",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Dessert",
                name="Babà Napoletano al Rum",
                description="Tradizionale babà lievitato naturalmente e inzuppato al rum con panna fresca montata.",
                price=6.50,
                allergens="glutine, lattosio, uova",
                is_vegetarian=True,
                is_vegan=False,
                is_gluten_free=False
            ),
            MenuItem(
                category="Dessert",
                name="Sorbetto al Limone di Sorrento",
                description="Fresco sorbetto preparato con limoni IGP della costiera amalfitana.",
                price=5.00,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),

            # Bevande
            MenuItem(
                category="Bevande",
                name="Acqua Minerale Naturale / Frizzante (0.75L)",
                description="Acqua in bottiglia di vetro.",
                price=2.50,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Bevande",
                name="Calice Falanghina del Sannio DOC",
                description="Vino bianco fresco e minerale ideale con pesce e primi.",
                price=5.50,
                allergens="solfiti",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Bevande",
                name="Calice Aglianico del Taburno DOCG",
                description="Vino rosso corposo e profumato perfetto per carni e formaggi stagionati.",
                price=6.00,
                allergens="solfiti",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            ),
            MenuItem(
                category="Bevande",
                name="Caffè Espresso Napoletano",
                description="Miscela arabica tostata secondo tradizione partenopea.",
                price=1.80,
                allergens="",
                is_vegetarian=True,
                is_vegan=True,
                is_gluten_free=True
            )
        ]
        db.add_all(menu_items)
        db.commit()

    # 3. Seed Restaurant Info
    if db.query(RestaurantInfo).count() == 0:
        info_list = [
            RestaurantInfo(
                key="name",
                value="Trattoria Bella Napoli",
                description="Nome ufficiale del ristorante"
            ),
            RestaurantInfo(
                key="address",
                value="Via Toledo 142, 80134 Napoli (NA)",
                description="Indirizzo e geolocalizzazione"
            ),
            RestaurantInfo(
                key="phone",
                value="+39 081 555 1234",
                description="Numero di telefono principale per prenotazioni e contatti"
            ),
            RestaurantInfo(
                key="email",
                value="prenotazioni@trattoriabellanapoli.it",
                description="Email aziendale"
            ),
            RestaurantInfo(
                key="opening_hours",
                value="Aperto dal Martedì alla Domenica. Turno pranzo: 12:00 - 15:00. Turno cena: 19:30 - 23:30. Lunedì giorno di chiusura settimanale.",
                description="Orari di apertura e turni"
            ),
            RestaurantInfo(
                key="parking",
                value="Disponibile convenzione con il 'Garage Toledo' a 50 metri dal locale (tariffa scontata di €3/ora per i clienti).",
                description="Indicazioni per parcheggio"
            ),
            RestaurantInfo(
                key="services",
                value="Aria condizionata in tutte le sale, tavoli all'aperto (terrazza e giardino estivo), WiFi gratuito, accesso facilitato per disabili, fasciatoio e seggioloni per bambini. Animali di piccola e media taglia ammessi.",
                description="Servizi offerti, accessibilità e policy animali"
            ),
            RestaurantInfo(
                key="payment_methods",
                value="Accettiamo contanti, carte di credito (Visa, Mastercard, Maestro, American Express), Bancomat, Apple Pay e Satispay.",
                description="Metodi di pagamento accettati"
            )
        ]
        db.add_all(info_list)
        db.commit()
