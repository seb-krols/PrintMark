"""License keys and the free monthly allowance.

BaseMark is free for noncommercial use (PolyForm Noncommercial 1.0.0, see LICENSE.md);
commercial use needs a paid license from the author. Without a key, BaseMark stamps up to
FREE_PER_MONTH exports per calendar month; after that, exports are left unchanged and the
notice says whom to contact. Keys are free for noncommercial groups (student teams, school
labs) and paid for businesses.

A key is a small signed statement ("licensed to …, until …"). The author signs it with a
private key that never leaves their computer (scripts/issue_license.py); BaseMark checks
it with the public key below. The source is open to read, so this is a clear reminder of
the license terms, not copy protection: the license itself is what counts.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from filelock import FileLock

from .config import atomic_write

CONTACT = "sebastians.krols@gmail.com"
FREE_PER_MONTH = 100
HEADS_UP = 20  # the stamped notice starts counting down this many exports before the limit
KEY_FILE = "license.key"
USAGE_FILE = "usage.json"
PREFIX = "BASEMARK-1"
# The author's public key. Keys signed by its private key unlock unlimited stamping.
PUBLIC_KEY = bytes.fromhex("39f78f03edde51a234c6a181b558bcff31bce35d5e8cd725872391ad8bb73031")
LIMIT_REACHED = "the free limit of"  # start of the skip reason; the notice uses it


# ---------- Ed25519 (RFC 8032 reference algorithm; small, no dependency) ----------

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    return _P - x if (x & 1) != sign else x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)
_IDENTITY = (0, 1, 1, 0)


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _multiply(scalar: int, point):
    result = _IDENTITY
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _same(p, q) -> bool:
    return (p[0] * q[2] - q[0] * p[2]) % _P == 0 and (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _encode(point) -> bytes:
    inverse = pow(point[2], _P - 2, _P)
    x, y = point[0] * inverse % _P, point[1] * inverse % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decode(data: bytes):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _hash(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def _expand(secret: bytes) -> tuple[int, bytes]:
    digest = hashlib.sha512(secret).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def public_key(secret: bytes) -> bytes:
    return _encode(_multiply(_expand(secret)[0], _G))


def sign(secret: bytes, message: bytes) -> bytes:
    scalar, prefix = _expand(secret)
    public = _encode(_multiply(scalar, _G))
    r = _hash(prefix + message) % _L
    encoded_r = _encode(_multiply(r, _G))
    s = (r + _hash(encoded_r + public + message) % _L * scalar) % _L
    return encoded_r + s.to_bytes(32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    point_a, point_r = _decode(public), _decode(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if point_a is None or point_r is None or s >= _L:
        return False
    h = _hash(signature[:32] + public + message) % _L
    return _same(_multiply(s, _G), _add(point_r, _multiply(h, point_a)))


# ---------- keys ----------


@dataclass(frozen=True)
class License:
    holder: str
    use: str  # "commercial", "noncommercial" (e.g. a student group), "owner"
    until: date | None
    key_id: str

    def describe(self) -> str:
        until = f" until {self.until.isoformat()}" if self.until else ""
        return f"Licensed to {self.holder} ({self.use}){until}"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_key(secret: bytes, holder: str, use: str, until: date | None, key_id: str) -> str:
    payload = json.dumps(
        {"holder": holder, "use": use, "until": until.isoformat() if until else None, "id": key_id},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"{PREFIX}.{_b64(payload)}.{_b64(sign(secret, payload))}"


def parse_key(text: str, public: bytes | None = None) -> License:
    """The license in a key; raises ValueError if it is not a genuine BaseMark key."""
    parts = "".join(text.split()).split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise ValueError("this is not a BaseMark license key")
    try:
        payload, signature = _unb64(parts[1]), _unb64(parts[2])
    except ValueError as exc:
        raise ValueError("the license key is incomplete; copy all of it") from exc
    if not verify(public or PUBLIC_KEY, payload, signature):
        raise ValueError("the license key is not valid (it may be mistyped)")
    data = json.loads(payload)
    until = date.fromisoformat(data["until"]) if data.get("until") else None
    return License(str(data["holder"]), str(data["use"]), until, str(data.get("id", "")))


# ---------- allowance ----------


@dataclass(frozen=True)
class Status:
    license: License | None
    problem: str  # why a saved key does not count, e.g. "expired on 2027-01-31"
    used: int  # stamped exports this calendar month

    @property
    def remaining(self) -> int | None:
        return None if self.license else max(0, FREE_PER_MONTH - self.used)

    @property
    def allowed(self) -> bool:
        return self.license is not None or self.used < FREE_PER_MONTH

    def describe(self) -> str:
        if self.license:
            return self.license.describe()
        text = f"Free use: {self.used} of {FREE_PER_MONTH} stamped exports this month"
        return f"{text} (saved key {self.problem})" if self.problem else text


def month(today: date | None = None) -> str:
    return (today or datetime.now().date()).strftime("%Y-%m")


def used_this_month(folder: Path, today: date | None = None) -> int:
    try:
        data = json.loads((folder / USAGE_FILE).read_text(encoding="utf-8"))
        return int(data["stamped"]) if data.get("month") == month(today) else 0
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def status(folder: Path, today: date | None = None, public: bytes | None = None) -> Status:
    today = today or datetime.now().date()
    used = used_this_month(folder, today)
    try:
        text = (folder / KEY_FILE).read_text(encoding="utf-8")
    except OSError:
        return Status(None, "", used)
    try:
        found = parse_key(text, public)
    except ValueError:
        return Status(None, "is not valid", used)
    if found.until and found.until < today:
        return Status(None, f"expired on {found.until.isoformat()}", used)
    return Status(found, "", used)


def limit_reason() -> str:
    return (
        f"{LIMIT_REACHED} {FREE_PER_MONTH} stamped exports this month is reached. For more, "
        "ask for a license key: free for noncommercial groups such as student teams and "
        f"school labs, paid for businesses. Contact {CONTACT}. Stamping starts again next "
        "month."
    )


def record_stamp(folder: Path, today: date | None = None) -> None:
    """Count one stamped export. Never raises: the export itself has already succeeded."""
    try:
        path = folder / USAGE_FILE
        with FileLock(str(path) + ".lock", timeout=2):
            data = {"month": month(today), "stamped": used_this_month(folder, today) + 1}
            atomic_write(path, json.dumps(data).encode("utf-8"))
    except Exception:
        pass


def install_key(folder: Path, text: str, public: bytes | None = None) -> License:
    found = parse_key(text, public)
    atomic_write(folder / KEY_FILE, ("".join(text.split()) + "\n").encode("ascii"))
    return found
