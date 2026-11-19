"""Create a self-signed certificate so the backend can be served over HTTPS (AMG-SR-001).

    python scripts/make_dev_cert.py            # writes dev-cert.pem and dev-key.pem here
    uvicorn app.main:app --port 8443 --ssl-keyfile dev-key.pem --ssl-certfile dev-cert.pem
    set FORCE_HTTPS=true                       # optional: redirect plain-HTTP requests to HTTPS

A self-signed certificate is for development: browsers warn about it. In production use a
certificate from a real authority (for example Let's Encrypt behind a reverse proxy).
Python's ssl module refuses protocols older than TLS 1.2 by default, so the server speaks TLS 1.2 or 1.3.
"""
import datetime
import ipaddress
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main(cert_path: str = "dev-cert.pem", key_path: str = "dev-key.pem") -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
        ))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"wrote {cert_path} and {key_path} (valid for one year, for localhost)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
