"""Application exceptions handled in app/main.py."""

from __future__ import annotations


class LoginRequired(Exception):
    """Raised by auth dependencies; redirects to the admin login page (?next=...)."""

    def __init__(self, next_url: str = "/admin") -> None:
        super().__init__(next_url)
        self.next_url = next_url


class TwoFactorSetupRequired(Exception):
    """Logged-in user without active 2FA (e.g. re-setup in progress) -> setup page."""


class FeatureLocked(Exception):
    """Feature not included in the active plan (admin: 403 page "Dostupno u paketu …")."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
