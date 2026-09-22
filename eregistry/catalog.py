from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Organisation:
    id: str
    name: str
    address: str = ""
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    folder: str = ""


class OrganisationCatalog:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "organisations.json"

    def list(self) -> list[Organisation]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Organisation(**item) for item in raw.get("organisations", [])]

    def save(self, organisations: list[Organisation]) -> None:
        self.path.write_text(
            json.dumps({"organisations": [asdict(x) for x in organisations]}, indent=2),
            encoding="utf-8",
        )

    def create(
        self,
        name: str,
        address: str = "",
        contact_person: str = "",
        phone: str = "",
        email: str = "",
    ) -> Organisation:
        name = " ".join(name.split())
        if not name:
            raise ValueError("Organisation name is required.")
        existing = self.list()
        if any(x.name.casefold() == name.casefold() for x in existing):
            raise ValueError("An organisation with this name already exists.")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "organisation"
        oid = uuid.uuid4().hex
        relative = str(Path("organisations") / f"{slug}-{oid[:8]}")
        folder = self.root / relative
        for child in ("photos", "pdfs"):
            (folder / child).mkdir(parents=True, exist_ok=True)
        org = Organisation(oid, name, address, contact_person, phone, email, relative)
        existing.append(org)
        self.save(existing)
        return org

    def folder_for(self, organisation: Organisation) -> Path:
        return self.root / organisation.folder
