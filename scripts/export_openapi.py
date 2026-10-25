"""Export the API's OpenAPI document for the frontend (HANDOFF-01).

Writes ``docs/api/openapi.json`` from fixed development settings, so the file never
depends on the local ``.env``: the routes are the ones a development server serves,
including the development-only fake gateway (``/payments/fake/...``). ``--check`` fails
when the committed file is out of date (a test runs the same comparison).

    python scripts/export_openapi.py [--check]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "api" / "openapi.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_spec() -> dict[str, Any]:
    from app.core.config import Environment, MediaStorage, PaymentGatewayName, Settings
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        # Explicit, so APP_NAME/APP_VERSION in the environment never change the file.
        app_name=Settings.model_fields["app_name"].default,
        app_version=Settings.model_fields["app_version"].default,
        database_url="postgresql+asyncpg://user:password@localhost:5432/project_ak",
        jwt_secret="openapi-export-secret-at-least-32-characters",
        environment=Environment.DEVELOPMENT,
        media_storage=MediaStorage.MEMORY,
        media_public_base_url="http://localhost:8000/media",
        media_allowed_hosts=["localhost"],
        payment_gateway=PaymentGatewayName.FAKE,
    )
    return create_app(settings).openapi()


def render(spec: dict[str, Any]) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    text = render(build_spec())
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT.relative_to(ROOT)} is out of date; run scripts/export_openapi.py")
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
