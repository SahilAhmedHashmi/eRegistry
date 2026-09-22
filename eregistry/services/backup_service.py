from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


class BackupService:
    def __init__(self, data_root: Path):
        self.data_root = data_root

    def create(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in self.data_root.rglob("*"):
                if not path.is_file() or "backups" in path.relative_to(self.data_root).parts:
                    continue
                archive.write(path, path.relative_to(self.data_root))
            archive.writestr(
                "backup_manifest.json",
                json.dumps(
                    {
                        "format": "eRegistry Backup",
                        "version": 1,
                        "created_at": datetime.utcnow().isoformat() + "Z",
                    },
                    indent=2,
                ),
            )
        return destination

    def restore(self, backup: Path) -> Path:
        with zipfile.ZipFile(backup) as archive:
            if "backup_manifest.json" not in archive.namelist():
                raise ValueError("This is not a valid eRegistry backup package.")
            for name in archive.namelist():
                candidate = (self.data_root / name).resolve()
                if (
                    self.data_root.resolve() not in candidate.parents
                    and candidate != self.data_root.resolve()
                ):
                    raise ValueError("Backup contains an unsafe path.")
        safety = (
            self.data_root / "backups" / f"pre_restore_{datetime.now():%Y%m%d_%H%M%S}.eregbackup"
        )
        self.create(safety)
        with tempfile.TemporaryDirectory() as temporary:
            extract = Path(temporary)
            with zipfile.ZipFile(backup) as archive:
                archive.extractall(extract)
            for child in self.data_root.iterdir():
                if child.name == "backups":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            for child in extract.iterdir():
                if child.name == "backup_manifest.json":
                    continue
                shutil.move(str(child), self.data_root / child.name)
        return safety
