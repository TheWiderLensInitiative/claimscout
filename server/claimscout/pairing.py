"""Phone pairing: a self-signed HTTPS certificate the phone pins by fingerprint, plus a random access token.

The pairing link carries the PC's addresses, the token and the certificate's SHA-256 fingerprint, so the
phone trusts exactly this PC and nobody on the Wi-Fi can read the traffic (email excerpts cross it).
"""
import datetime as dt
import hashlib
import ipaddress
import secrets
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .db import HOME

CERT, KEY = HOME / "tls/cert.pem", HOME / "tls/key.pem"


def ensure_cert() -> tuple[Path, Path]:
    if CERT.exists() and KEY.exists():
        return CERT, KEY
    CERT.parent.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ClaimScout on " + socket.gethostname())])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
            .sign(key, hashes.SHA256()))
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    KEY.chmod(0o600)
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return CERT, KEY


def fingerprint() -> str:
    """SHA-256 of the certificate (DER), lowercase hex — what the phone compares against."""
    ensure_cert()
    der = x509.load_pem_x509_certificate(CERT.read_bytes()).public_bytes(serialization.Encoding.DER)
    return hashlib.sha256(der).hexdigest()


def token(db) -> str:
    t = db.get("token")
    if not t:
        t = secrets.token_urlsafe(32)
        db.put("token", t)
    return t


def reset_token(db) -> str:
    db.put("token", None)
    return token(db)


def addresses() -> list[str]:
    """This PC's LAN IP and, if Tailscale is installed, its Tailscale IP (for use away from home)."""
    out = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            out.append(s.getsockname()[0])
    except OSError:
        pass
    if shutil.which("tailscale"):
        try:
            ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.split()
            out += [i for i in ip if i not in out]
        except (OSError, subprocess.SubprocessError):
            pass
    return out or ["127.0.0.1"]


def link(db, port: int) -> str:
    q = [("u", f"https://{a}:{port}") for a in addresses()] + [("t", token(db)), ("f", fingerprint())]
    return "claimscout://pair?" + urlencode(q)


def qr_svg(data: str) -> str:
    import io
    import qrcode
    import qrcode.image.svg
    buf = io.BytesIO()
    qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).save(buf)
    return buf.getvalue().decode()
