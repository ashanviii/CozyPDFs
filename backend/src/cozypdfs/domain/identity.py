from itsdangerous import BadSignature, TimestampSigner
from sqlalchemy.orm import Session

from cozypdfs.db.models import Identity

COOKIE_NAME = "cozy_identity"


class IdentityService:
    """Resolves the anonymous Identity behind a request.

    The browser only ever holds a signed *pointer* (the cookie value) — the
    actual library, progress, bookmarks, etc. live server-side against the
    Identity row. This is what lets a real account later "claim" an
    anonymous identity (Identity.claimed_by_user_id) instead of migrating
    every table when accounts ship.
    """

    def __init__(self, secret_key: str):
        self._signer = TimestampSigner(secret_key)

    def resolve(self, db: Session, cookie_value: str | None) -> tuple[Identity, str]:
        """Returns (identity, cookie_value_to_set). Always issues a
        (possibly unchanged) cookie value the caller should set on the
        response — this both refreshes anonymous identities and repairs
        missing/tampered cookies transparently."""
        identity_id = self._verify(cookie_value) if cookie_value else None
        identity = db.get(Identity, identity_id) if identity_id else None

        if identity is None:
            identity = Identity()
            db.add(identity)
            db.flush()

        return identity, self._sign(identity.id)

    def _sign(self, identity_id: str) -> str:
        return self._signer.sign(identity_id).decode()

    def _verify(self, cookie_value: str) -> str | None:
        try:
            return self._signer.unsign(cookie_value, max_age=None).decode()
        except BadSignature:
            return None
