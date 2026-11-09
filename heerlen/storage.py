"""Non-sensitive user settings and Windows Credential Manager integration."""
from __future__ import annotations

import json
import os
from pathlib import Path

SERVICE = "TeamspeakHeerlenPC"
ACCOUNT = "ClientQueryApiKey"


def settings_path() -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    return root / "TeamspeakHeerlenPC" / "settings.json"


def load_settings() -> dict:
    try:
        loaded = json.loads(settings_path().read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(config: dict) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in config.items() if k in {"view", "window_geometry"}}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(safe, indent=2), encoding="utf-8")
    temporary.replace(path)


def get_api_key() -> str:
    try:
        import keyring
        return keyring.get_password(SERVICE, ACCOUNT) or ""
    except Exception:
        return ""


def set_api_key(value: str) -> bool:
    try:
        import keyring
        if value.strip():
            keyring.set_password(SERVICE, ACCOUNT, value.strip())
        else:
            try:
                keyring.delete_password(SERVICE, ACCOUNT)
            except keyring.errors.PasswordDeleteError:
                pass
        return True
    except Exception:
        return False
