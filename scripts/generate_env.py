"""Create a local .env from .env.example with random passwords and keys.

    python scripts/generate_env.py            # refuses to overwrite an existing .env
    python scripts/generate_env.py --force

OKX facilitator credentials and payout wallet are left empty on purpose:
add your own values by hand.
"""

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = {
    "MYSQL_PASSWORD": lambda: secrets.token_urlsafe(18),
    "REDIS_PASSWORD": lambda: secrets.token_urlsafe(18),
    "RABBITMQ_PASSWORD": lambda: secrets.token_urlsafe(18),
    "PAYMENT_CONFIG_SECRET_KEY": lambda: base64.b64encode(os.urandom(32)).decode(),
}


def main() -> None:
    target = ROOT / ".env"
    if target.exists() and "--force" not in sys.argv:
        sys.exit(".env already exists (use --force to overwrite)")
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip()
        if key in GENERATED and not line.startswith("#"):
            line = f"{key}={GENERATED[key]()}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {target} (git-ignored). Add OKX_* credentials and a payout wallet yourself.")


if __name__ == "__main__":
    main()
