"""Read-only normal-app/protocol baseline; no credential contents are exported."""

import hashlib
import json
import os
import sys
import winreg
from pathlib import Path


def snapshot():
    registry = {}
    for label, hive in [
        ("HKCU", winreg.HKEY_CURRENT_USER),
        ("HKLM", winreg.HKEY_LOCAL_MACHINE),
    ]:
        for sub in [
            "Software\\Classes\\saiia",
            "Software\\Classes\\saiia\\shell\\open\\command",
        ]:
            try:
                with winreg.OpenKey(hive, sub) as key:
                    values = []
                    for n in range(winreg.QueryInfoKey(key)[1]):
                        values.append(list(winreg.EnumValue(key, n)))
                    registry[label + "/" + sub] = values
            except FileNotFoundError:
                registry[label + "/" + sub] = None
    sessions = {}
    for base in [Path(os.environ["APPDATA"]), Path(os.environ["LOCALAPPDATA"])]:
        for directory in base.iterdir():
            if directory.is_dir() and directory.name.lower() in (
                "frontend",
                "saiia",
                "intervucopilot",
            ):
                for file in directory.rglob("desktop-auth-session.bin"):
                    sessions[str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
    return {"protocol_registry": registry, "normal_auth_session_hashes": sessions}


if __name__ == "__main__":
    current = snapshot()
    p = Path(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] == "--compare":
        assert current == json.loads(p.read_text()), (
            "Normal protocol/auth snapshot changed"
        )
        print("Normal protocol registration and auth session hashes unchanged.")
    else:
        p.write_text(json.dumps(current, indent=2), encoding="utf-8")
        print("Normal protocol/auth baseline recorded without secret contents.")
