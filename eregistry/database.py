from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, OrganisationProfile


def organisation_db_key(master_key: bytes, organisation_id: str) -> bytes:
    return hashlib.sha256(master_key + organisation_id.encode("utf-8") + b"eRegistry-db").digest()


class DatabaseManager:
    def __init__(self, path: Path, key: bytes):
        self.path = path
        self.key = key
        self.engine = self._make_engine()
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _make_engine(self) -> Engine:
        try:
            from sqlcipher3 import dbapi2 as sqlcipher
        except ImportError as exc:
            raise RuntimeError(
                "SQLCipher support is unavailable. Install sqlcipher3-wheels from requirements.txt."
            ) from exc

        self.path.parent.mkdir(parents=True, exist_ok=True)
        key_hex = self.key.hex()

        def creator():
            connection = sqlcipher.connect(str(self.path))
            connection.execute(f"PRAGMA key = \"x'{key_hex}'\"")
            connection.execute("PRAGMA cipher_compatibility = 4")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("SELECT count(*) FROM sqlite_master")
            return connection

        engine = create_engine("sqlite://", creator=creator, future=True)

        @event.listens_for(engine, "connect")
        def _foreign_keys(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        return engine

    def initialize(self, profile: dict) -> None:
        Base.metadata.create_all(self.engine)
        with self.session() as session:
            existing = session.get(OrganisationProfile, 1)
            if existing is None:
                session.add(OrganisationProfile(id=1, **profile))
                session.commit()

    def session(self) -> Session:
        return self.Session()

    def close(self) -> None:
        self.engine.dispose()
