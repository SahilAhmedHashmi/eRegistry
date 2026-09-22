from pathlib import Path

from eregistry.services.backup_service import BackupService


def test_restore_replaces_data_and_creates_safety_copy(tmp_path: Path):
    root = tmp_path / "data"
    (root / "backups").mkdir(parents=True)
    (root / "value.txt").write_text("old")
    service = BackupService(root)
    package = tmp_path / "saved.eregbackup"
    service.create(package)
    (root / "value.txt").write_text("new")
    safety = service.restore(package)
    assert (root / "value.txt").read_text() == "old"
    assert safety.exists()
