import os

# The pre-existing tests book with made-up customer ids ("anon_user_123", ...), so they run with the
# registration requirement OFF (legacy behaviour). tests/test_customers.py switches it ON explicitly
# with monkeypatch to test the real, default behaviour. Must be set before backend.config is imported.
os.environ.setdefault("REQUIRE_CUSTOMER_REGISTRATION", "false")
