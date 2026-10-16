"""TLS certificate for the BE gateway, so the microphone works from the CHAT and VOICE PCs.

Browsers expose the microphone only to *secure contexts*. ``https://`` is one (even before the certificate is trusted: the
page loads after the operator accepts the warning once per browser), ``http://<LAN-IP>`` is not. The gateway therefore
serves HTTPS on the LAN.

The certificate is a self-signed server certificate whose SubjectAltName lists every name the gateway is reached by
(loopback, ``*.localhost``, this PC's hostname and IPs). It is regenerated when that list changes (new IP) and lives in
``lan/tls/`` (git-ignored: private key material never goes to the repository).

Production note: replace it with a certificate from the organisation's internal CA (or mkcert on the operators' PCs) by
dropping ``gateway.pem`` / ``gateway.key`` in ``lan/tls/``; this module never overwrites files whose SAN list it did not write.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TLS_DIR = ROOT / "lan" / "tls"
CERT = TLS_DIR / "gateway.pem"
KEY = TLS_DIR / "gateway.key"
SAN_FILE = TLS_DIR / "gateway.san.json"


def names_for(extra_ips: list[str]) -> list[str]:
    """Every DNS name / IP the gateway can be reached by."""
    names = ["localhost", "completo.localhost", "solo-be.localhost", "127.0.0.1", "::1"]
    try:
        names.append(socket.gethostname())
    except OSError:
        pass
    names += [ip for ip in extra_ips if ip]
    seen: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def _san_entries(names: list[str]) -> tuple[list[str], list[str]]:
    dns, ips = [], []
    for name in names:
        try:
            ipaddress.ip_address(name)
            ips.append(name)
        except ValueError:
            dns.append(name)
    return dns, ips


def _with_cryptography(names: list[str]) -> bool:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return False
    dns, ips = _san_entries(names)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AI4Restaurants gateway")])
    now = dt.datetime.now(dt.timezone.utc)
    san = [x509.DNSName(d) for d in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
    return True


def _openssl_binary() -> str:
    found = shutil.which("openssl")
    if found:
        return found
    for candidate in (r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if Path(candidate).is_file():
            return candidate
    return ""


def _with_openssl(names: list[str]) -> bool:
    exe = _openssl_binary()
    if not exe:
        return False
    dns, ips = _san_entries(names)
    san = ",".join([f"DNS:{d}" for d in dns] + [f"IP:{i}" for i in ips])
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [exe, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "825", "-sha256",
               "-keyout", str(KEY), "-out", str(CERT), "-subj", "/CN=AI4Restaurants gateway",
               "-addext", f"subjectAltName={san}", "-addext", "basicConstraints=CA:FALSE"]
        result = subprocess.run(cmd, cwd=tmp, capture_output=True, timeout=60)  # noqa: S603
    return result.returncode == 0 and CERT.is_file() and KEY.is_file()


def ensure_certificate(extra_ips: list[str]) -> tuple[Path, Path] | None:
    """Return (cert, key), creating or refreshing them. None when no tool can create one (the gateway then serves HTTP)."""
    names = names_for(extra_ips)
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    if CERT.is_file() and KEY.is_file():
        if not SAN_FILE.is_file():
            return CERT, KEY  # supplied by the operator (internal CA, mkcert...): never overwritten
        try:
            known = json.loads(SAN_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            known = []
        if set(names) <= set(known):
            return CERT, KEY
    if _with_cryptography(names) or _with_openssl(names):
        SAN_FILE.write_text(json.dumps(names), encoding="utf-8")
        return CERT, KEY
    return None
