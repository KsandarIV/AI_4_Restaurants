"""Where are the other two machines? Service discovery for a three-node LAN, without hand-edited IP lists.

Problem this solves: ``lan/lan_config.json`` ships *example* addresses (192.168.1.x). On a real LAN (10.10.x.x) every
component that used them silently pointed at a dead host. Addresses are therefore never trusted, they are *verified*.

Resolution order for the host of a peer role (first one that PASSES the health probe wins):

  1. ``AI4R_<ROLE>_HOST``  environment variable            (explicit operator override)
  2. ``lan/peers.json``    local cache, written by this module (git-ignored)
  3. the address in ``lan/lan_config.json``                  (only if it answers: examples never do)
  4. an active scan of the local /24 networks (this PC's and the BE's), 128 parallel probes, ~2-4 s, bounded

A probe is a TCP+HTTP request to the role's well-known port whose answer must carry the role's *signature*
(a field only that service returns), so a stray web server on the same port is never mistaken for the peer.
A verified result is cached; a cached result that stops answering is dropped and rediscovered.

Operator tools (stdlib only):
    python -m showcase.peers show                       what is known and whether it answers now
    python -m showcase.peers set voice 10.10.95.50      pin a peer (verified first)
    python -m showcase.peers scan                       force a rediscovery
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PEERS_FILE = ROOT / "lan" / "peers.json"
CONFIG_FILE = ROOT / "lan" / "lan_config.json"

# role -> (port, path, JSON key that only this service returns)
SIGNATURE: dict[str, tuple[int, str, str]] = {
    "be": (8000, "/api/health", "restaurant"),
    "chat": (8002, "/health", "be_url"),
    "voice": (8003, "/site/config", "require_registration"),
}
ROLES = tuple(SIGNATURE)


def probe(role: str, host: str, timeout: float = 3.0) -> bool:
    """True when ``host`` runs ``role``: the answer must be JSON carrying the role's signature key."""
    port, path, key = SIGNATURE[role]
    try:
        with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as resp:
            body: Any = json.loads(resp.read(65536).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - refused, timed out, not JSON...: not this service
        return False
    return isinstance(body, dict) and key in body


def _load() -> dict[str, str]:
    try:
        data = json.loads(PEERS_FILE.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(peers: dict[str, str]) -> None:
    PEERS_FILE.write_text(json.dumps(peers, indent=2), encoding="utf-8")


def cached(role: str) -> str:
    """The cached (not re-verified) host of ``role``, or ''."""
    return _load().get(role, "")


def remember(role: str, host: str) -> None:
    """Persist a verified peer."""
    peers = _load()
    if peers.get(role) != host:
        peers[role] = host
        _save(peers)


def forget(role: str) -> None:
    """Drop a cached peer that stopped answering."""
    peers = _load()
    if peers.pop(role, None) is not None:
        _save(peers)


def _config_host(role: str) -> str:
    try:
        node = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get(role, {})
        return str(node.get("host", ""))
    except (OSError, ValueError, AttributeError):
        return ""


def networks(own_ip: str, be_host: str) -> list[ipaddress.IPv4Network]:
    """The /24 networks worth scanning: this PC's and the BE's (both are known to be on the LAN)."""
    nets: list[ipaddress.IPv4Network] = []
    for ip in (own_ip, be_host):
        try:
            net = ipaddress.ip_network(f"{ip}/24", strict=False)
        except ValueError:
            continue
        if isinstance(net, ipaddress.IPv4Network) and net not in nets and not net.is_loopback:
            nets.append(net)
    return nets


def scan(role: str, nets: list[ipaddress.IPv4Network], timeout: float = 0.5) -> str:
    """Probe every host of ``nets`` for ``role`` in parallel; first verified host wins."""
    port = SIGNATURE[role][0]

    def open_port(ip: str) -> str:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                pass
        except OSError:
            return ""
        return ip if probe(role, ip, timeout=3.0) else ""

    hosts = ["127.0.0.1"] + [str(h) for net in nets for h in net.hosts()]  # loopback first: a service on this very PC
    with ThreadPoolExecutor(max_workers=128) as pool:
        for found in pool.map(open_port, hosts):
            if found:
                return found
    return ""


def resolve(role: str, own_role: str = "", own_ip: str = "", be_host: str = "", allow_scan: bool = False) -> str:
    """Verified host of ``role`` ('' when unknown). ``own_role`` always resolves to loopback."""
    if role == own_role:
        return "127.0.0.1"
    env = os.environ.get(f"AI4R_{role.upper()}_HOST", "").strip()
    if role == "be" and be_host:
        env = env or be_host  # the BE address is the one every machine was configured with (.env)
    for candidate in (env, cached(role), _config_host(role)):
        if candidate and probe(role, candidate):
            remember(role, candidate)
            return candidate
    if cached(role):
        forget(role)  # it stopped answering: do not keep serving a dead address
    if allow_scan:
        found = scan(role, networks(own_ip, be_host))
        if found:
            remember(role, found)
            return found
    return ""


def _be_host_from_env() -> str:
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("BACKEND_BASE_URL="):
                return line.split("=", 1)[1].strip().split("://")[-1].split(":")[0].split("/")[0]
    except OSError:
        pass
    return ""


def _own_ip() -> str:
    try:
        return str(json.loads((ROOT / "lan" / "macchina.json").read_text(encoding="utf-8")).get("host", ""))
    except (OSError, ValueError):
        return ""


def main(argv: list[str] | None = None) -> int:
    """CLI: show | set ROLE IP | scan."""
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else "show"
    own_ip, be_host = _own_ip(), _be_host_from_env()
    if cmd == "set" and len(args) == 3 and args[1] in ROLES:
        if not probe(args[1], args[2], timeout=3.0):
            print(f"[peers] {args[2]} does not answer as '{args[1]}' (port {SIGNATURE[args[1]][0]}): not saved.")
            return 1
        remember(args[1], args[2])
        print(f"[peers] {args[1]} = {args[2]} saved in {PEERS_FILE.name}")
        return 0
    if cmd == "scan":
        for role in ("voice", "chat"):
            print(f"[peers] {role}: {resolve(role, allow_scan=True, own_ip=own_ip, be_host=be_host) or 'NOT FOUND'}")
        return 0
    if cmd == "show":
        print(f"[peers] own ip: {own_ip or '?'}   BE (.env): {be_host or '?'}   networks: {[str(n) for n in networks(own_ip, be_host)]}")
        for role in ROLES:
            host = resolve(role, be_host=be_host)
            print(f"[peers] {role:<6} {host or 'unknown'}  ({'answers' if host else 'no answer; run: python -m showcase.peers scan'})")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
