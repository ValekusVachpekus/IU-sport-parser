from __future__ import annotations


class SportError(Exception):
    """Base error for the sport client."""


class AuthError(SportError):
    """Login/token acquisition failed (bad credentials, ROPC disabled, etc.)."""


class AuthExpired(SportError):
    """Access token rejected (401); caller should refresh/relogin."""


class CheckInError(SportError):
    """check_in returned a 4xx business error."""

    def __init__(self, code: int | None, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


class AlreadyCheckedIn(CheckInError):
    pass


class CannotCheckIn(CheckInError):
    """Server says check-in not currently allowed (full / outside window / limits)."""
