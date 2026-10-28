"""Encryption at rest: AES-GCM, purpose-bound and rotatable; the database never holds plain text."""

import base64

import pytest
from sqlalchemy import text

from isd import crypto
from isd.models import Base, Contact, Message
from isd.services import key_rotation
from tests.conftest import NOW

K1 = base64.b64encode(b"1" * 32).decode()
K2 = base64.b64encode(b"2" * 32).decode()
# Rows already committed in the test database (seed data) use the development key.
DEV = base64.b64encode(crypto._DEV_KEY).decode()


@pytest.fixture
def keys(monkeypatch):
    def use(raw: str, active: str):
        monkeypatch.setenv("ENCRYPTION_KEYS", raw)
        monkeypatch.setenv("ENCRYPTION_ACTIVE_KEY_ID", active)

    use(f"k1:{K1}", "k1")
    return use


def test_round_trip_nonce_and_prefix(keys):
    a, b = crypto.encrypt("hello", "messages.body"), crypto.encrypt("hello", "messages.body")
    assert a != b and a.startswith("enc1:k1:") and "hello" not in a
    assert crypto.decrypt(a, "messages.body") == "hello"


def test_a_value_is_bound_to_its_column_and_tampering_is_detected(keys):
    v = crypto.encrypt("555-0100", "contacts.phone_ref")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(v, "messages.body")  # moved to another column
    head, _, tail = v.rpartition(":")
    flipped = head + ":" + ("A" if tail[0] != "A" else "B") + tail[1:]
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(flipped, "contacts.phone_ref")


def test_plain_text_written_before_encryption_is_still_readable(keys):
    assert crypto.decrypt("old plain value", "messages.body") == "old plain value"
    assert crypto.needs_rotation("old plain value")


def test_bad_key_configuration_is_refused(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEYS", "k1:" + base64.b64encode(b"short").decode())
    with pytest.raises(crypto.CryptoError):
        crypto.keyring()
    monkeypatch.setenv("ENCRYPTION_KEYS", f"k1:{K1}")
    monkeypatch.setenv("ENCRYPTION_ACTIVE_KEY_ID", "nope")
    with pytest.raises(crypto.CryptoError):
        crypto.keyring()


def test_the_database_holds_ciphertext_and_the_app_sees_plain_text(owner, make_resident, keys):
    rid = make_resident()
    c = Contact(
        resident_id=rid,
        name="Fam",
        type="family",
        phone_ref="555-0142",
        approved=True,
        status="approved",
    )
    owner.add(c)
    owner.flush()
    m = Message(
        resident_id=rid,
        contact_id=c.id,
        direction="out",
        body="a private line",
        privileged=False,
        monitored=True,
        created_at=NOW,
    )
    owner.add(m)
    owner.flush()
    raw_phone = owner.execute(
        text("SELECT phone_ref FROM contacts WHERE id = :i"), {"i": c.id}
    ).scalar()
    raw_body = owner.execute(text("SELECT body FROM messages WHERE id = :i"), {"i": m.id}).scalar()
    assert raw_phone.startswith("enc1:") and "555-0142" not in raw_phone
    assert raw_body.startswith("enc1:") and "private" not in raw_body
    owner.expire_all()
    assert owner.get(Contact, c.id).phone_ref == "555-0142"
    assert owner.get(Message, m.id).body == "a private line"
    # the searchable keyed hash is stored, not the number
    assert owner.get(Contact, c.id).phone_hash == crypto.blind_index("555-0142")


def test_the_staff_mfa_secret_and_call_references_are_encrypted_columns():
    cols = {(t, c) for t, c, _ in key_rotation.ENCRYPTED_COLUMNS}
    from isd.crypto import EncryptedText

    found = {
        (t.name, col.name)
        for t in Base.metadata.sorted_tables
        for col in t.columns
        if isinstance(col.type, EncryptedText)
    }
    assert cols == found, "the rotation list must match the encrypted columns in the models"


def test_rotation_moves_every_value_to_the_new_key_and_old_values_stay_readable(
    owner, make_resident, keys
):
    rid = make_resident()
    c = Contact(
        resident_id=rid,
        name="Fam",
        type="family",
        phone_ref="555-0177",
        approved=True,
        status="approved",
    )
    owner.add(c)
    owner.flush()
    assert (
        crypto.key_id_of(
            owner.execute(text("SELECT phone_ref FROM contacts WHERE id=:i"), {"i": c.id}).scalar()
        )
        == "k1"
    )
    keys(f"k1:{K1},k2:{K2},dev1:{DEV}", "k2")  # add a new key and make it active
    assert key_rotation.pending(owner)["contacts.phone_ref"] >= 1
    owner.expire_all()
    assert owner.get(Contact, c.id).phone_ref == "555-0177"  # still readable before rotating
    key_rotation.rotate_all(owner)
    assert sum(key_rotation.pending(owner).values()) == 0
    raw = owner.execute(text("SELECT phone_ref FROM contacts WHERE id=:i"), {"i": c.id}).scalar()
    assert crypto.key_id_of(raw) == "k2"
    keys(f"k2:{K2},dev1:{DEV}", "k2")  # the old key can now be retired
    owner.expire_all()
    assert owner.get(Contact, c.id).phone_ref == "555-0177"
