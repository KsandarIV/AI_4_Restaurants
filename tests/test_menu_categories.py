import pytest
from backend.database.connection import SessionLocal
from backend.database.crud import get_menu_items, init_db


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


@pytest.mark.parametrize("word,category", [("dolci", "Dessert"), ("Dolce", "Dessert"), ("dessert", "Dessert"),
                                           ("vini", "Bevande"), ("primo", "Primi"), ("Secondi", "Secondi")])
def test_category_synonyms(word, category):
    with SessionLocal() as db:
        items = get_menu_items(db, category=word)
        assert items and {i["category"] for i in items} == {category}
