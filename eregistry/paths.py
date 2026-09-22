from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .constants import APP_NAME


def app_config_dir() -> Path:
    if os.environ.get("EREGISTRY_CONFIG_DIR"):
        return Path(os.environ["EREGISTRY_CONFIG_DIR"]).expanduser().resolve()
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / APP_NAME


def bootstrap_path() -> Path:
    return app_config_dir() / "bootstrap.json"


def save_root_pointer(data_root: Path) -> None:
    target = bootstrap_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"data_root": str(data_root.resolve())}, indent=2), encoding="utf-8"
    )


def load_root_pointer() -> Path | None:
    target = bootstrap_path()
    if not target.exists():
        return None
    try:
        value = json.loads(target.read_text(encoding="utf-8"))["data_root"]
        return Path(value).expanduser().resolve()
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def ensure_data_layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("organisations", "backups", "reports"):
        (root / name).mkdir(exist_ok=True)
