from __future__ import annotations

import base64
import json
import secrets
import string
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _derive(secret: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(secret.encode("utf-8"))


def _wrap(master: bytes, secret: str, salt: bytes) -> str:
    nonce = secrets.token_bytes(12)
    return _b64(nonce + AESGCM(_derive(secret, salt)).encrypt(nonce, master, b"eRegistry-v1"))


def _unwrap(payload: str, secret: str, salt: bytes) -> bytes:
    raw = _unb64(payload)
    return AESGCM(_derive(secret, salt)).decrypt(raw[:12], raw[12:], b"eRegistry-v1")


def generate_recovery_key() -> str:
    alphabet = string.ascii_uppercase + string.digits
    groups = ["".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(6)]
    return "-".join(groups)


@dataclass
class AuthStore:
    path: Path

    @property
    def configured(self) -> bool:
        return self.path.exists()

    def setup(self, password: str, recovery_key: str | None = None) -> tuple[bytes, str]:
        if len(password) < 8:
            raise ValueError("Password must contain at least 8 characters.")
        recovery_key = recovery_key or generate_recovery_key()
        master = secrets.token_bytes(32)
        password_salt = secrets.token_bytes(16)
        recovery_salt = secrets.token_bytes(16)
        verifier_salt = secrets.token_bytes(16)
        verifier = _derive(password, verifier_salt)
        data = {
            "version": 1,
            "password_salt": _b64(password_salt),
            "recovery_salt": _b64(recovery_salt),
            "verifier_salt": _b64(verifier_salt),
            "verifier": _b64(verifier),
            "wrapped_master_password": _wrap(master, password, password_salt),
            "wrapped_master_recovery": _wrap(master, recovery_key, recovery_salt),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return master, recovery_key

    def unlock(self, password: str) -> bytes:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        expected = _unb64(data["verifier"])
        actual = _derive(password, _unb64(data["verifier_salt"]))
        if not secrets.compare_digest(expected, actual):
            raise ValueError("Incorrect password.")
        try:
            return _unwrap(data["wrapped_master_password"], password, _unb64(data["password_salt"]))
        except InvalidTag as exc:
            raise ValueError("Authentication data is invalid or damaged.") from exc

    def reset_with_recovery(self, recovery_key: str, new_password: str) -> bytes:
        if len(new_password) < 8:
            raise ValueError("Password must contain at least 8 characters.")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        try:
            master = _unwrap(
                data["wrapped_master_recovery"],
                recovery_key.strip().upper(),
                _unb64(data["recovery_salt"]),
            )
        except InvalidTag as exc:
            raise ValueError("Invalid recovery key.") from exc
        password_salt = secrets.token_bytes(16)
        verifier_salt = secrets.token_bytes(16)
        data.update(
            password_salt=_b64(password_salt),
            verifier_salt=_b64(verifier_salt),
            verifier=_b64(_derive(new_password, verifier_salt)),
            wrapped_master_password=_wrap(master, new_password, password_salt),
        )
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return master

    def change_password(self, old_password: str, new_password: str) -> None:
        master = self.unlock(old_password)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        password_salt = secrets.token_bytes(16)
        verifier_salt = secrets.token_bytes(16)
        data.update(
            password_salt=_b64(password_salt),
            verifier_salt=_b64(verifier_salt),
            verifier=_b64(_derive(new_password, verifier_salt)),
            wrapped_master_password=_wrap(master, new_password, password_salt),
        )
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
