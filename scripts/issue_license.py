"""Create BaseMark license keys (for the author only).

One-time setup, creates the private signing key OUTSIDE the repository:
    python scripts/issue_license.py --new-signing-key "D:/keys/basemark-signing-key.txt"
  then put the printed public key into PUBLIC_KEY in src/basemark/licensing.py.

Issue a key (signing key from --signing-key or the BASEMARK_SIGNING_KEY variable):
    python scripts/issue_license.py --holder "Acme Inc." --use commercial --until 2027-12-31
    python scripts/issue_license.py --holder "UBC Formula Racing" --use noncommercial

Keep the signing key secret and backed up (e.g. in a password manager). Anyone with it can
create keys; without it no new keys can be made for the released versions.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from basemark.licensing import PUBLIC_KEY, make_key, parse_key, public_key  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--new-signing-key", type=Path, metavar="FILE")
    parser.add_argument("--signing-key", type=Path, default=os.environ.get("BASEMARK_SIGNING_KEY"))
    parser.add_argument("--holder", help="who the license is for, as it should be shown")
    parser.add_argument(
        "--use", choices=["commercial", "noncommercial", "owner"], default="commercial"
    )
    parser.add_argument("--until", type=date.fromisoformat, help="last valid day, YYYY-MM-DD")
    args = parser.parse_args()

    if args.new_signing_key:
        target = args.new_signing_key.resolve()
        if ROOT in target.parents:
            parser.error("keep the signing key outside the repository")
        if target.exists():
            parser.error(f"{target} exists; refusing to overwrite a signing key")
        secret = secrets.token_bytes(32)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(secret.hex() + "\n", encoding="ascii")
        print(f"Signing key written to {target}. Back it up; never commit it.")
        print(f"Public key for licensing.py: {public_key(secret).hex()}")
        return 0

    if not args.signing_key or not args.holder:
        parser.error("--signing-key (or BASEMARK_SIGNING_KEY) and --holder are required")
    secret = bytes.fromhex(Path(args.signing_key).read_text(encoding="ascii").strip())
    if public_key(secret) != PUBLIC_KEY:
        parser.error("this signing key does not match PUBLIC_KEY in licensing.py")
    key = make_key(secret, args.holder, args.use, args.until, secrets.token_hex(4))
    print(parse_key(key).describe())
    print(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
