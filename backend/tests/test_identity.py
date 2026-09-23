from cozypdfs.domain.identity import IdentityService


def test_no_cookie_creates_new_identity(db_session):
    service = IdentityService("test-secret")
    identity, cookie_value = service.resolve(db_session, None)
    assert identity.id
    assert cookie_value


def test_valid_cookie_resolves_same_identity(db_session):
    service = IdentityService("test-secret")
    identity, cookie_value = service.resolve(db_session, None)

    again, _ = service.resolve(db_session, cookie_value)
    assert again.id == identity.id


def test_tampered_cookie_falls_back_to_new_identity(db_session):
    service = IdentityService("test-secret")
    identity, cookie_value = service.resolve(db_session, None)

    tampered, _ = service.resolve(db_session, cookie_value + "tampered")
    assert tampered.id != identity.id


def test_cookie_signed_with_different_secret_is_rejected(db_session):
    service_a = IdentityService("secret-a")
    service_b = IdentityService("secret-b")

    identity, cookie_value = service_a.resolve(db_session, None)
    resolved, _ = service_b.resolve(db_session, cookie_value)

    assert resolved.id != identity.id
