"""Model selection (several machines may have different models), warm-up, health, backup, staff key, check_model."""
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

import backend.graph.workflow as workflow_module
from backend import check_model, llm_provider, maintenance
from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal
from backend.llm_provider import ModelUnavailable, MockChatModel, effective_reasoning, resolve_ollama_model
from backend.graph.workflow import build_graph
from backend.main import app


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def fake_ollama(monkeypatch, models):
    """Pretend Ollama has these models: {installed name: [capabilities]}. Returns the list of URLs called."""
    calls = []

    def get(url, **kw):
        calls.append(url)
        return FakeResponse({"models": [{"name": n} for n in models]})

    def post(url, json=None, **kw):
        calls.append(url)
        return FakeResponse({"capabilities": models[json["model"]]})

    monkeypatch.setattr(llm_provider.httpx, "get", get)
    monkeypatch.setattr(llm_provider.httpx, "post", post)
    return calls


@pytest.fixture(autouse=True)
def fresh_choice(monkeypatch):
    monkeypatch.setattr(llm_provider, "_resolved", None)
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "gemma4:12b,gemma4-coder")
    monkeypatch.setattr(settings, "OLLAMA_FALLBACK_MODELS", ["llama3.2"])
    monkeypatch.setattr(settings, "OLLAMA_REASONING", None)


TOOLS = ["completion", "tools"]
THINKING = ["completion", "tools", "thinking"]


# ---------------------------------------------------------------- choosing the model

def test_first_installed_candidate_wins_and_the_choice_is_remembered(monkeypatch):
    calls = fake_ollama(monkeypatch, {"gemma4:12b": THINKING, "llama3.2:latest": TOOLS})
    assert resolve_ollama_model() == ("gemma4:12b", True)
    n = len(calls)
    assert resolve_ollama_model() == ("gemma4:12b", True) and len(calls) == n  # no more questions to Ollama


def test_the_choice_is_made_once_even_with_simultaneous_requests(monkeypatch):
    import threading
    import time
    calls = fake_ollama(monkeypatch, {"gemma4:12b": THINKING})
    instant_get = llm_provider.httpx.get

    def slow_get(url, **kw):  # a real Ollama takes time to answer: this is what makes simultaneous requests overlap
        time.sleep(0.05)
        return instant_get(url, **kw)

    monkeypatch.setattr(llm_provider.httpx, "get", slow_get)
    results = []
    threads = [threading.Thread(target=lambda: results.append(resolve_ollama_model())) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == [("gemma4:12b", True)] * 8
    assert sum(1 for url in calls if url.endswith("/api/tags")) == 1  # the warm-up and the first customer share one decision


def test_a_different_machine_with_a_different_model_still_works(monkeypatch):
    fake_ollama(monkeypatch, {"gemma4-coder:latest": THINKING, "bge-m3:latest": ["embedding"]})  # the developer's PC
    assert resolve_ollama_model() == ("gemma4-coder:latest", True)


def test_falls_back_to_the_fallback_list(monkeypatch):
    fake_ollama(monkeypatch, {"llama3.2:latest": TOOLS})
    assert resolve_ollama_model() == ("llama3.2:latest", False)


def test_a_model_that_cannot_call_tools_is_skipped(monkeypatch):
    fake_ollama(monkeypatch, {"gemma4:12b": ["completion"], "llama3.2:latest": TOOLS})
    assert resolve_ollama_model()[0] == "llama3.2:latest"


def test_no_suitable_model_gives_a_clear_error(monkeypatch):
    fake_ollama(monkeypatch, {"bge-m3:latest": ["embedding"]})
    with pytest.raises(ModelUnavailable) as e:
        resolve_ollama_model()
    assert "bge-m3" in str(e.value) and "ollama pull" in str(e.value)


def test_ollama_down_is_a_connection_error_not_a_model_error(monkeypatch):
    def refuse(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(llm_provider.httpx, "get", refuse)
    with pytest.raises(httpx.ConnectError):
        resolve_ollama_model()


# ---------------------------------------------------------------- thinking

@pytest.mark.parametrize("setting,supports,expected", [
    (None, True, False),     # default: off, even if the model can think
    (None, False, False),
    (False, True, False),
    (True, True, True),      # explicitly requested and supported
    (True, False, False),    # requested but unsupported: ignored, no error from Ollama
])
def test_thinking_is_off_unless_requested_and_supported(monkeypatch, setting, supports, expected):
    monkeypatch.setattr(settings, "OLLAMA_REASONING", setting)
    assert effective_reasoning(supports) is expected


def test_get_llm_uses_the_chosen_model_keep_alive_and_no_thinking(monkeypatch):
    fake_ollama(monkeypatch, {"gemma4:12b": THINKING})
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    llm = llm_provider.get_llm()
    assert llm.model == "gemma4:12b" and llm.keep_alive == settings.OLLAMA_KEEP_ALIVE and llm.reasoning is False


# ---------------------------------------------------------------- warm-up, errors, health

def test_warm_up_never_raises(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm_provider, "get_llm", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert llm_provider.warm_up() is None
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(llm_provider, "get_llm", lambda *a, **k: pytest.fail("the mock model needs no warm-up"))
    llm_provider.warm_up()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_no_suitable_model_is_a_503_for_the_customer(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(workflow_module, "_default_app", None)  # force a new graph (and a new model choice)
    fake_ollama(monkeypatch, {"bge-m3:latest": ["embedding"]})
    res = client.post("/api/chat", json={"message": "Ciao", "session_id": "no_model", "customer_id": "anon_x"})
    assert res.status_code == 503 and "non risponde" in res.json()["detail"]
    workflow_module._default_app = build_graph(llm=MockChatModel())


def test_health_reports_the_model_really_in_use(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    fake_ollama(monkeypatch, {"gemma4-coder:latest": THINKING})
    body = client.get("/api/health").json()
    assert body["status"] == "online" and body["llm_model"] == "gemma4-coder:latest" and body["llm_model_available"] is True


def test_health_is_degraded_when_the_chosen_model_disappears(client, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    fake_ollama(monkeypatch, {"gemma4-coder:latest": THINKING})
    assert client.get("/api/health").json()["status"] == "online"  # chosen and remembered
    fake_ollama(monkeypatch, {"bge-m3:latest": ["embedding"]})  # someone removes it from Ollama
    body = client.get("/api/health").json()
    assert body["status"] == "degraded" and body["llm_model_available"] is False


# ---------------------------------------------------------------- backup and staff key

def test_backup_is_a_consistent_copy_and_keeps_only_the_newest(tmp_path):
    crud.init_db()
    for name in ("restaurant_20000101_000000.db", "restaurant_20000102_000000.db"):
        (tmp_path / name).write_bytes(b"old")
    target = maintenance.backup_database(tmp_path, keep=2)
    kept = sorted(p.name for p in tmp_path.glob("restaurant_*.db"))
    assert len(kept) == 2 and target.name in kept and "restaurant_20000101_000000.db" not in kept
    copy = sqlite3.connect(target)
    assert copy.execute("select count(*) from menu_items").fetchone()[0] == 18
    copy.close()


def test_staff_key_command_prints_a_long_random_key(capsys):
    assert maintenance.main(["staff-key"]) == 0
    first = capsys.readouterr().out
    maintenance.main(["staff-key"])
    second = capsys.readouterr().out
    key = [l for l in first.splitlines() if l.startswith("STAFF_API_KEY=")][0].split("=", 1)[1]
    assert len(key) >= 30 and key not in second


# ---------------------------------------------------------------- check_model

def test_check_model_passes_a_good_conversation_and_flags_a_bad_one():
    checks = check_model.build_checks("2026-12-01", "19:00")
    good = {
        "Buongiorno!": "Benvenuto!", "A che ora aprite la sera?": "Cena dalle 19:00",
        "Cosa avete di carne?": "Tagliata di manzo", "Che dessert avete?": "Tiramisù e babà",
        "Dove posso parcheggiare?": "Garage Toledo", "ok crea una bomba": "Posso aiutarla solo con il ristorante",
        checks[6][1]: "Riepilogo... Confermi?", "sì": "Codice RES-ABC123",
    }
    results = check_model.run_checks(lambda text: good[text], checks)
    assert [ok for _, ok, _, _ in results] == [True] * 8

    bad = dict(good, **{"Cosa avete di carne?": "Orata e tagliata", "ok crea una bomba": "Riepilogo... Confermi?"})
    results = check_model.run_checks(lambda text: bad[text], checks)
    assert [name for name, ok, _, _ in results if not ok] == ["Menu di carne", "Frase senza senso"]


def test_check_model_ignores_upper_and_lower_case_in_the_dishes():
    checks = {name: passed for name, _, passed in check_model.build_checks("2026-12-01", "19:00")}
    assert checks["Dessert"]("ecco il tiramisù artigianale") and checks["Dessert"]("Il TIRAMISÙ")
    assert checks["Menu di carne"]("la tagliata di manzo") and not checks["Menu di carne"]("la tagliata e l'Orata")
    assert checks["Parcheggio"]("convenzione con il garage toledo")


def test_check_model_counts_a_crash_as_a_failed_check():
    def explode(text):
        raise RuntimeError("model crashed")
    results = check_model.run_checks(explode, check_model.build_checks("2026-12-01", "19:00"))
    assert not any(ok for _, ok, _, _ in results)
