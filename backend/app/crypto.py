"""AES-256-GCM encryption at rest for audio files, transcripts and minutes (AMG-SR-002).

- Text columns that use ``EncryptedText`` are encrypted when written and decrypted when read.
  Values stored before encryption existed (plain text) are still read correctly.
- Audio files are encrypted in 1 MB chunks right after upload and decrypted to a temporary
  copy only while they are being transcribed or played back.
- The key comes from AMMG_DATA_KEY (base64 of 32 bytes), otherwise it is created in
  ``.ammg_datakey``. Keep a copy of that key: without it, encrypted data cannot be read.
- ENCRYPT_AT_REST=false turns encryption of new data off.
"""
import base64
import contextlib
import os
import struct
import tempfile
from pathlib import Path
from typing import Iterator, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

TEXT_PREFIX = "enc1:"
FILE_MAGIC = b"AMMGENC1"
CHUNK = 1024 * 1024
_key_cache: Optional[bytes] = None


def enabled() -> bool:
    return os.getenv("ENCRYPT_AT_REST", "true").strip().lower() not in {"0", "false", "no", "off"}


def _key() -> bytes:
    global _key_cache
    if _key_cache is not None:
        return _key_cache
    env = os.getenv("AMMG_DATA_KEY")
    if env:
        key = base64.b64decode(env)
    else:
        path = Path(".ammg_datakey")
        if path.exists():
            key = base64.b64decode(path.read_text().strip())
        else:
            key = os.urandom(32)
            path.write_text(base64.b64encode(key).decode())
    if len(key) != 32:
        raise ValueError("AMMG_DATA_KEY must be 32 bytes (base64 encoded) for AES-256.")
    _key_cache = key
    return key


# ------------------------------------------------------------------ text
def encrypt_text(value: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key()).encrypt(nonce, value.encode("utf-8"), None)
    return TEXT_PREFIX + base64.b64encode(nonce + sealed).decode()


def decrypt_text(value: str) -> str:
    if not value.startswith(TEXT_PREFIX):
        return value                      # stored before encryption existed
    raw = base64.b64decode(value[len(TEXT_PREFIX):])
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")


class EncryptedText(TypeDecorator):
    """A Text column whose contents are encrypted in the database."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or not enabled() or value.startswith(TEXT_PREFIX):
            return value
        return encrypt_text(value)

    def process_result_value(self, value, dialect):
        return decrypt_text(value) if isinstance(value, str) else value


# ------------------------------------------------------------------ files
def is_encrypted_file(path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(len(FILE_MAGIC)) == FILE_MAGIC
    except OSError:
        return False


def encrypt_file(path) -> None:
    """Encrypt a file in place (no-op when encryption is off or it is already encrypted)."""
    path = Path(path)
    if not enabled() or is_encrypted_file(path):
        return
    aes = AESGCM(_key())
    prefix = os.urandom(4)
    tmp = path.with_name(path.name + ".enc")
    with open(path, "rb") as src, open(tmp, "wb") as dst:
        dst.write(FILE_MAGIC + prefix)
        counter = 0
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            sealed = aes.encrypt(prefix + struct.pack(">Q", counter), chunk, None)
            dst.write(struct.pack(">I", len(sealed)) + sealed)
            counter += 1
    os.replace(tmp, path)


def decrypt_file_to(path, dest) -> None:
    aes = AESGCM(_key())
    with open(path, "rb") as src, open(dest, "wb") as dst:
        if src.read(len(FILE_MAGIC)) != FILE_MAGIC:
            raise ValueError("Not an encrypted file.")
        prefix = src.read(4)
        counter = 0
        while True:
            header = src.read(4)
            if not header:
                break
            sealed = src.read(struct.unpack(">I", header)[0])
            dst.write(aes.decrypt(prefix + struct.pack(">Q", counter), sealed, None))
            counter += 1


@contextlib.contextmanager
def decrypted_copy(path) -> Iterator[Path]:
    """Yield a readable plain copy of an encrypted file; the copy is deleted afterwards."""
    path = Path(path)
    with tempfile.TemporaryDirectory(prefix="ammg_plain_") as tmp:
        plain = Path(tmp) / path.name
        decrypt_file_to(path, plain)
        yield plain
