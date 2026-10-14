"""POS token round-trips: device tokens and pos_session tokens, and that neither can impersonate
the other (same type-confusion guard every other token kind in this codebase already has)."""

import pytest

from app.core.security import (
    create_access_token,
    create_device_token,
    create_guest_token,
    create_pos_session_token,
    decode_device_token,
    decode_pos_session_token,
)


def test_device_token_round_trips():
    token = create_device_token(device_id=7, restaurant_id=42)
    payload = decode_device_token(token)
    assert payload["sub"] == "7" and payload["tenant"] == 42 and payload["type"] == "device"


def test_pos_session_token_round_trips():
    token = create_pos_session_token(device_id=7, staff_user_id=99, restaurant_id=42)
    payload = decode_pos_session_token(token)
    assert payload["sub"] == "99" and payload["device"] == 7 and payload["tenant"] == 42 and payload["type"] == "pos_session"


def test_a_device_token_is_refused_as_a_pos_session_token():
    token = create_device_token(device_id=7, restaurant_id=42)
    with pytest.raises(ValueError):
        decode_pos_session_token(token)


def test_a_pos_session_token_is_refused_as_a_device_token():
    token = create_pos_session_token(device_id=7, staff_user_id=99, restaurant_id=42)
    with pytest.raises(ValueError):
        decode_device_token(token)


def test_an_ordinary_access_token_is_refused_as_a_device_token():
    token = create_access_token("1", claims={"role": "RESTAURANT_ADMIN", "tenant": None})
    with pytest.raises(ValueError):
        decode_device_token(token)


def test_a_guest_table_pass_is_refused_as_a_device_token():
    token = create_guest_token(guest_id=1, session_id=2, restaurant_id=3)
    with pytest.raises(ValueError):
        decode_device_token(token)
