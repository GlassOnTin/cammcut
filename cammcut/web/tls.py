"""Self-signed TLS for the LAN endpoint.

Browsers increasingly upgrade http:// to https:// automatically, keeping
the port — so the app serves TLS on the same port and the upgrade lands on
a real TLS listener (the user accepts the self-signed certificate once).
The certificate is generated on first run with openssl and covers the
machine's hostnames and current IPv4 addresses.
"""

import datetime
import ipaddress
import os
import socket
import subprocess
from pathlib import Path

CERT_PATH = Path("data/tls/cert.pem")
KEY_PATH = Path("data/tls/key.pem")


def _interface_ips() -> set[str]:
    """IPv4 addresses of this machine's network interfaces (SIOCGIFADDR)."""
    import fcntl
    import struct
    ips = set()
    try:
        ifaces = os.listdir("/sys/class/net")
    except OSError:
        return ips
    for iface in ifaces:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                packed = fcntl.ioctl(
                    s.fileno(), 0x8915,  # SIOCGIFADDR
                    struct.pack("256s", iface[:15].encode()))
            ip = socket.inet_ntoa(packed[20:24])
        except OSError:
            continue
        if not ip.startswith("127."):
            ips.add(ip)
    return ips


def san_entries() -> list[str]:
    """Hostnames + this machine's IPv4 addresses, deduplicated."""
    entries = {"DNS:localhost", "IP:127.0.0.1"}
    host = socket.gethostname()
    if host:
        entries.add("DNS:%s" % host)
        if "." not in host:
            entries.add("DNS:%s.lan" % host)
    for ip in _interface_ips():
        entries.add("IP:%s" % ipaddress.ip_address(ip))
    return sorted(entries)


def generate_cert(cert_path: Path = CERT_PATH, key_path: Path = KEY_PATH) -> None:
    """Create a 10-year self-signed certificate via openssl."""
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cn = socket.gethostname() or "cammcut"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:P-256",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", "3650", "-nodes",
            "-subj", "/CN=%s" % cn,
            "-addext", "subjectAltName=%s" % ",".join(san_entries()),
        ],
        capture_output=True, text=True, check=True, timeout=30,
    )


def ensure_cert(cert_path: Path = CERT_PATH, key_path: Path = KEY_PATH) -> tuple[Path, Path]:
    """Return usable cert/key paths, generating them on first run.

    Returns (None, None) when openssl is unavailable so the caller can fall
    back to plain HTTP rather than fail to start.
    """
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    try:
        generate_cert(cert_path, key_path)
    except (OSError, subprocess.SubprocessError):
        return None, None
    return cert_path, key_path


def not_after(cert_path: Path = CERT_PATH) -> datetime.datetime | None:
    """Certificate expiry, for the README / a future status line."""
    try:
        r = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", str(cert_path)],
            capture_output=True, text=True, check=True, timeout=10)
        # "notAfter=Sep  7 12:00:00 2036 GMT"
        return datetime.datetime.strptime(
            r.stdout.strip().split("=", 1)[1], "%b %d %H:%M:%S %Y %Z"
        ).replace(tzinfo=datetime.timezone.utc)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None