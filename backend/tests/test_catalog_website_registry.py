"""Website registry mirror must match the authoritative pure domain contract."""

import json
from dataclasses import asdict
from pathlib import Path

from app.commercial import catalog_contract as c


def test_website_registry_matches_domain():
    registry = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "frontend/src/auth/catalogRegistry.json"
        ).read_text()
    )
    assert registry == {
        "version": c.REGISTRY_VERSION,
        "currencies": dict(c.CURRENCIES),
        "auto_basis": c.AUTO_BASIS,
        "features": list(c.FEATURES),
        "meters": {k: asdict(v) for k, v in c.METERS.items()},
    }
