import atexit
import os
import shutil
import tempfile
from pathlib import Path

# The tests NEVER touch the development database: they get a throw-away folder with their own
# restaurant.db and conversations.db. This must happen before backend.config is imported.
_TMP = Path(tempfile.mkdtemp(prefix="ristorante_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'restaurant.db').as_posix()}"
os.environ["CHECKPOINTS_DB_PATH"] = str(_TMP / "conversations.db")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

# No Ollama needed to run the tests: the health check and the default graph use the mock model.
os.environ["LLM_PROVIDER"] = "mock"
os.environ["STAFF_API_KEY"] = "test-staff-key"

# The pre-existing tests book with made-up customer ids ("anon_user_123", ...), so they run with the
# registration requirement OFF (legacy behaviour). tests/test_customers.py switches it ON explicitly
# with monkeypatch to test the real, default behaviour.
os.environ["REQUIRE_CUSTOMER_REGISTRATION"] = "false"
