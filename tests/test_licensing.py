"""License keys and the free monthly allowance."""

from __future__ import annotations

import json
from datetime import date

import pytest

from basemark import licensing
from basemark.__main__ import main
from basemark.errors import SafeSkip
from basemark.licensing import make_key, parse_key, public_key, sign, status, verify
from basemark.notify import texts
from basemark.service import process

# RFC 8032 section 7.1, tests 1 and 2.
VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39"
        "701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f36"
        "13d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
]
SECRET = bytes(range(32))  # a test signing key, not the author's
PUBLIC = public_key(SECRET)


@pytest.mark.parametrize(("secret", "public", "message", "signature"), VECTORS)
def test_ed25519_matches_rfc_8032(secret, public, message, signature):
    secret, public, message, signature = map(bytes.fromhex, (secret, public, message, signature))
    assert public_key(secret) == public
    assert sign(secret, message) == signature
    assert verify(public, message, signature)
    assert not verify(public, message + b"!", signature)
    assert not verify(public, message, signature[:-1] + bytes([signature[-1] ^ 1]))


def test_keys_round_trip_and_reject_tampering():
    key = make_key(SECRET, "Maker Lab, Acme Inc.", "commercial", date(2027, 12, 31), "k1")
    found = parse_key(key, PUBLIC)
    assert found.describe() == "Licensed to Maker Lab, Acme Inc. (commercial) until 2027-12-31"
    assert parse_key("  " + key[:40] + "\n" + key[40:] + " ", PUBLIC) == found  # pasted lines
    with pytest.raises(ValueError, match="not valid"):
        parse_key(key, licensing.PUBLIC_KEY)  # signed by a different key
    prefix, payload, signature = key.split(".")
    forged = licensing._b64(licensing._unb64(payload).replace(b"2027", b"2099"))
    with pytest.raises(ValueError, match="not valid"):
        parse_key(f"{prefix}.{forged}.{signature}", PUBLIC)
    with pytest.raises(ValueError, match="not a BaseMark"):
        parse_key("hello", PUBLIC)


def test_status_free_licensed_expired_and_invalid(tmp_path):
    today = date(2026, 10, 28)
    assert status(tmp_path, today).describe() == "Free use: 0 of 100 stamped exports this month"
    (tmp_path / licensing.KEY_FILE).write_text(
        make_key(SECRET, "Lab", "commercial", date(2026, 10, 1), "k2")
    )
    expired = status(tmp_path, today, PUBLIC)
    assert expired.license is None and "expired on 2026-10-01" in expired.describe()
    licensing.install_key(tmp_path, make_key(SECRET, "Lab", "owner", None, "k3"), PUBLIC)
    assert status(tmp_path, today, PUBLIC).describe() == "Licensed to Lab (owner)"
    assert status(tmp_path, today).problem == "is not valid"  # wrong public key


def test_usage_counts_per_month(tmp_path):
    october, november = date(2026, 10, 28), date(2026, 11, 1)
    for _ in range(3):
        licensing.record_stamp(tmp_path, october)
    assert licensing.used_this_month(tmp_path, october) == 3
    assert licensing.used_this_month(tmp_path, november) == 0
    licensing.record_stamp(tmp_path, november)
    assert json.loads((tmp_path / licensing.USAGE_FILE).read_text()) == {
        "month": "2026-11",
        "stamped": 1,
    }


def test_limit_leaves_exports_unchanged_and_a_key_lifts_it(job_file, tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    (tmp_path / licensing.USAGE_FILE).write_text(
        json.dumps({"month": licensing.month(), "stamped": licensing.FREE_PER_MONTH})
    )
    original = job_file.read_bytes()
    with pytest.raises(SafeSkip, match="free limit of 100"):
        process(job_file, config, {"mode": "auto"}, {})
    assert job_file.read_bytes() == original
    assert process(job_file, config, {"mode": "auto"}, {}, dry_run=True).status == "preview"
    monkeypatch.setattr(licensing, "PUBLIC_KEY", PUBLIC)
    licensing.install_key(tmp_path, make_key(SECRET, "Shop", "commercial", None, "k4"))
    assert process(job_file, config, {"mode": "auto"}, {}).status == "stamped"


def test_countdown_before_the_limit(job_file, tmp_path):
    left = licensing.HEADS_UP + 1
    (tmp_path / licensing.USAGE_FILE).write_text(
        json.dumps({"month": licensing.month(), "stamped": licensing.FREE_PER_MONTH - left})
    )
    result = process(job_file, tmp_path / "config.toml", {"mode": "auto"}, {})
    assert result.message.endswith(f"{left - 1} of 100 free stamps left this month.")
    tone, title, _ = texts("stamped", result.message)
    assert (tone, title) == ("ok", "Stamped PLA")


def test_limit_notice():
    tone, title, body = texts("skipped", f"skipped — {licensing.limit_reason()}")
    assert (tone, title) == ("warn", "Free monthly limit reached")
    assert licensing.CONTACT in body


def test_cli_installs_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(licensing, "PUBLIC_KEY", PUBLIC)
    config = tmp_path / "config.toml"
    assert main(["--config", str(config), "--license-key", "nonsense"]) == 1
    key = make_key(SECRET, "UBC Formula Racing", "noncommercial", None, "k5")
    assert main(["--config", str(config), "--license-key", key]) == 0
    assert "Licensed to UBC Formula Racing (noncommercial)" in capsys.readouterr().out
