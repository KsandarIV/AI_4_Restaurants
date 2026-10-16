"""The complete site and the LAN peer discovery (showcase/): verified addresses, no stale IPs, safe static serving."""

from __future__ import annotations

import ipaddress
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from showcase import launcher, peers, serve  # noqa: E402
from voicebot import peers_file  # noqa: E402


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _json_server(body: dict[str, object], path: str = "/") -> tuple[ThreadingHTTPServer, int]:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            data = json.dumps(body).encode()
            self.send_response(200 if self.path == path else 404)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server, url = _serve(H)
    return server, int(url.rsplit(":", 1)[1])


@pytest.fixture()
def isolated_peers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    file = tmp_path / "peers.json"
    monkeypatch.setattr(peers, "PEERS_FILE", file)
    monkeypatch.setattr(peers, "_config_host", lambda role: "")
    for role in peers.ROLES:
        monkeypatch.delenv(f"AI4R_{role.upper()}_HOST", raising=False)
    return file


# ---------------- the complete site ----------------


@pytest.fixture()
def site(monkeypatch: pytest.MonkeyPatch) -> str:
    resolver = serve.VoiceResolver("http://10.0.0.7:8003", "", "")
    server, url = _serve(serve.make_handler(resolver, "http://10.0.0.9:8000"))
    yield url  # type: ignore[misc]
    server.shutdown()


def test_index_is_pointed_at_the_voice_pc_and_carries_the_operator_tools(site: str) -> None:
    status, html = _get(site + "/")
    assert status == 200
    assert 'window.VOICE_BASE = "http://10.0.0.7:8003"' in html
    assert html.index("VOICE_BASE") < html.index("/site-assets/app.js")  # set before the script runs
    for link in ('href="/staff.html"', 'href="http://10.0.0.9:8000/docs"', 'href="http://10.0.0.9:8000/api/health"',
                 'href="http://10.0.0.7:8003/diag"', 'href="http://10.0.0.7:8003/test-voice"'):
        assert link in html, link


def test_staff_area_is_served_with_the_real_be_address(site: str) -> None:
    assert "Area ristoratore" in _get(site + "/staff.html")[1]
    config = _get(site + "/js/config.js")[1]
    assert 'baseUrl: "http://10.0.0.9:8000"' in config and "10.10.95.34" not in config
    assert _get(site + "/js/staff.js")[0] == 200 and _get(site + "/css/style.css")[0] == 200


def test_assets_are_served_and_paths_cannot_escape(site: str) -> None:
    assert _get(site + "/site-assets/app.js")[0] == 200 and _get(site + "/site-assets/site.css")[0] == 200
    health = json.loads(_get(site + "/health")[1])
    assert health["version"] == serve.VERSION
    for bad in ("/site-assets/../../../../../.env", "/site-assets/%2e%2e/%2e%2e/server.py", "/js/../../.env",
                "/css/../README.md", "/nothing"):
        assert _get(site + bad)[0] == 404, bad


def test_an_unreachable_voice_pc_is_a_visible_warning_not_a_dead_page() -> None:
    html = serve.render_index("", "http://10.0.0.9:8000").decode()
    assert "window.VOICE_BASE = \"\"" in html and "Il PC della voce non risponde" in html
    assert "showcase.peers set voice" in html  # tells the operator what to do


def test_the_voice_pc_is_resolved_per_request_not_frozen_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["", "10.0.0.7"])
    monkeypatch.setattr(peers, "resolve", lambda *a, **k: next(answers))
    resolver = serve.VoiceResolver("", "10.0.0.2", "10.0.0.9")
    assert resolver.base() == ""  # voice PC not up yet
    monkeypatch.setattr(serve, "_TTL_S", -1)  # the cache entry is considered expired
    assert resolver.base() == "http://10.0.0.7:8003"  # it came up later: no restart needed


# ---------------- peer discovery ----------------


def test_probe_requires_the_role_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    server, port = _json_server({"status": "ok", "be_url": "http://x"}, "/health")
    monkeypatch.setitem(peers.SIGNATURE, "chat", (port, "/health", "be_url"))
    assert peers.probe("chat", "127.0.0.1")
    monkeypatch.setitem(peers.SIGNATURE, "chat", (port, "/health", "restaurant"))  # right port, wrong service
    assert not peers.probe("chat", "127.0.0.1")
    server.shutdown()
    assert not peers.probe("chat", "127.0.0.1")  # nobody listening


def test_resolution_verifies_caches_and_forgets(isolated_peers: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server, port = _json_server({"language": "it", "require_registration": True}, "/site/config")
    monkeypatch.setitem(peers.SIGNATURE, "voice", (port, "/site/config", "require_registration"))
    monkeypatch.setenv("AI4R_VOICE_HOST", "127.0.0.1")
    assert peers.resolve("voice") == "127.0.0.1" and json.loads(isolated_peers.read_text())["voice"] == "127.0.0.1"
    monkeypatch.delenv("AI4R_VOICE_HOST")
    assert peers.resolve("voice") == "127.0.0.1"  # now from the cache, verified again
    server.shutdown()
    assert peers.resolve("voice") == "" and "voice" not in json.loads(isolated_peers.read_text())  # dead: dropped


def test_example_addresses_in_lan_config_are_never_trusted(isolated_peers: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(peers, "_config_host", lambda role: "192.168.1.12")  # the shipped example
    assert peers.resolve("voice") == ""  # nothing answers there: unresolved, not "resolved to a dead host"


def test_own_role_is_loopback_and_the_be_comes_from_env(isolated_peers: Path) -> None:
    assert peers.resolve("voice", own_role="voice") == "127.0.0.1"


def test_scan_finds_the_peer_inside_the_local_24(monkeypatch: pytest.MonkeyPatch) -> None:
    server, port = _json_server({"status": "ok", "be_url": "x"}, "/health")
    monkeypatch.setitem(peers.SIGNATURE, "chat", (port, "/health", "be_url"))
    assert peers.scan("chat", [ipaddress.ip_network("127.0.0.0/24")], timeout=0.3) == "127.0.0.1"
    server.shutdown()
    assert peers.scan("chat", [ipaddress.ip_network("127.0.0.0/30")], timeout=0.2) == ""


def test_networks_are_the_own_and_the_be_24() -> None:
    nets = [str(n) for n in peers.networks("10.10.95.40", "10.10.96.7")]
    assert nets == ["10.10.95.0/24", "10.10.96.0/24"]
    assert peers.networks("garbage", "") == []


def test_peers_cli_refuses_to_pin_a_host_that_does_not_answer(
    isolated_peers: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(peers.SIGNATURE, "voice", (9, "/site/config", "require_registration"))  # a port nobody serves
    assert peers.main(["set", "voice", "127.0.0.1"]) == 1  # nothing speaks the voice protocol on 8003 here
    assert not isolated_peers.exists() and "not saved" in capsys.readouterr().out


# ---------------- the voice server finds the CHAT PC lazily ----------------


def test_voice_server_chat_bridge_prefers_the_configured_url_then_the_verified_peer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "peers.json"
    monkeypatch.setenv("AI4R_PEERS_FILE", str(file))
    assert peers_file.chat_service_url("") == ""  # file absent
    file.write_text(json.dumps({"chat": "10.10.95.60"}))
    assert peers_file.chat_service_url("") == "http://10.10.95.60:8002"
    assert peers_file.chat_service_url("http://pinned:8002/") == "http://pinned:8002"  # .env wins
    file.write_text("not json")
    assert peers_file.chat_service_url("") == ""  # a broken file never crashes a request


# ---------------- launcher ----------------


def test_addresses_are_the_easy_ones_and_every_role_opens_test_page_and_complete_site() -> None:
    be = launcher.names("be", "10.10.95.34")
    assert be["solo-be"] == "http://solo-be.localhost:8080/"
    assert be["completo"] == "https://completo.localhost:8090/"  # the BE reaches its own gateway through *.localhost
    assert launcher.names("chat", "10.10.95.34")["completo"] == "https://10.10.95.34:8090/"  # the others go to the BE
    assert launcher.names("voice", "10.10.95.34")["completo"] == "https://10.10.95.34:8090/"
    assert launcher.names("chat", "")["chat"] == "http://chat.localhost:8080/"
    assert launcher.names("voice", "")["voce"] == "http://voce.localhost:8003/test-voice"
    assert launcher.OPEN == {"be": ["solo-be", "completo"], "chat": ["chat", "completo"], "voice": ["voce", "completo"]}


def test_the_complete_site_is_probed_on_the_be_not_locally_for_chat_and_voice() -> None:
    assert launcher.probes("be", "10.10.95.34")["completo"] == "https://127.0.0.1:8090/health"
    assert launcher.probes("voice", "10.10.95.34")["completo"] == "https://10.10.95.34:8090/health"


def test_tabs_open_when_the_servers_answer_and_a_dead_one_is_reported(monkeypatch: pytest.MonkeyPatch,
                                                                       capsys: pytest.CaptureFixture[str]) -> None:
    server, url = _serve(serve.make_handler(serve.VoiceResolver("http://x:8003", "", ""), ""))
    opened: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    urls = {"completo": "https://be:8090/", "chat": "http://chat.localhost:8080/"}
    probes = {"completo": url + "/health", "chat": "http://127.0.0.1:9/"}  # the second never answers
    launcher._wait_and_open(["completo"], urls, probes, timeout_s=5)
    assert opened == ["https://be:8090/"]
    ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(ticks))
    launcher._wait_and_open(["chat"], urls, probes, timeout_s=10)
    assert "non ha risposto" in capsys.readouterr().out
    server.shutdown()


def test_a_stale_server_on_the_gateway_port_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    class Old(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            body = b'{"status":"ok","version":2}'  # the previous showcase server: no "gateway", version 2
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server, url = _serve(Old)
    monkeypatch.setattr(launcher, "GATEWAY_PORT", int(url.rsplit(":", 1)[1]))
    assert launcher._gateway_is_current() is False
    server.shutdown()


def test_the_launcher_starts_no_local_copy_of_the_site_on_chat_and_voice() -> None:
    text = (ROOT / "showcase" / "launcher.py").read_text(encoding="utf-8")
    assert 'if role == "be":' in text and "gateway.py" in text
    assert "serve.py" not in text and "AI4R_PEERS_FILE" not in text  # star topology: nothing peer-to-peer


def test_the_machine_setup_hook_exists_and_cannot_stop_a_component() -> None:
    text = (ROOT / "lan" / "machine_setup.py").read_text(encoding="utf-8")
    assert "from showcase.launcher import start_showcase" in text
    assert "showcase non avviato" in text  # failure is logged, the component still starts
