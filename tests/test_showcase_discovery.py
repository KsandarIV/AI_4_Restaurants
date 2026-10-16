"""Showcase: discovery on a /22 LAN and the CHAT/VOICE self-announcement to the BE gateway."""

from __future__ import annotations

import ipaddress

import pytest
from fastapi.testclient import TestClient

from showcase import gateway, peers


def test_networks_cover_the_whole_slash22():
    """CHAT 10.10.92.x, VOICE 10.10.93.x, BE 10.10.95.x: a /22 holds all three, a /24 would find none of them."""
    nets = peers.networks("10.10.95.34", "10.10.95.34", prefix=22)
    assert nets == [ipaddress.ip_network("10.10.92.0/22")]
    assert ipaddress.ip_address("10.10.92.246") in nets[0]
    assert ipaddress.ip_address("10.10.93.153") in nets[0]


def test_networks_scan_is_capped():
    """An absurd mask (/8) never turns into a multi-million host scan."""
    (net,) = peers.networks("10.10.95.34", "10.10.95.34", prefix=8)
    assert net.prefixlen == peers.SCAN_MIN_PREFIX


def test_networks_unknown_mask_falls_back_to_slash24_floor():
    assert peers.networks("10.10.95.34", "", prefix=24) == [ipaddress.ip_network("10.10.95.0/24")]


@pytest.fixture
def gw(tmp_path, monkeypatch):
    """Gateway with a throw-away peers cache and a fake probe (no network)."""
    monkeypatch.setattr(peers, "PEERS_FILE", tmp_path / "peers.json")
    monkeypatch.setattr(peers, "probe", lambda role, host, timeout=3.0: host.startswith("10.10.") and host != "10.10.0.0")
    voice, chat = gateway.PeerCache("voice", "10.10.95.34", "10.10.95.34"), gateway.PeerCache("chat", "10.10.95.34", "10.10.95.34")
    app = gateway.create_gateway("http://127.0.0.1:1", voice, chat)
    with TestClient(app, client=("10.10.93.153", 5000)) as client:
        yield client, voice


def test_register_caches_the_caller_address(gw):
    client, voice = gw
    r = client.post("/register", params={"role": "voice"})
    assert r.status_code == 200 and r.json() == {"role": "voice", "host": "10.10.93.153"}
    assert peers.cached("voice") == "10.10.93.153"
    assert voice() == "http://10.10.93.153:8003"


def test_register_rejects_a_service_that_does_not_answer_yet(gw, monkeypatch):
    client, _ = gw
    monkeypatch.setattr(peers, "probe", lambda *a, **k: False)
    r = client.post("/register", params={"role": "chat"})
    assert r.status_code == 409
    assert peers.cached("chat") == ""


def test_register_rejects_unknown_roles(gw):
    client, _ = gw
    assert client.post("/register", params={"role": "be"}).status_code == 400
