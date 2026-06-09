"""Log in to the Innopolis sport site and capture its session cookie.

The sport OAuth client is *confidential* (it has a client_secret we don't possess),
so we cannot exchange the authorization code ourselves. Instead we drive the whole
browser flow through the site itself:

  GET  /oauth2/login                 -> site stores OAuth `state`, 302 to ADFS
  (follow) -> ADFS forms-login page  -> POST UserName/Password
  (follow) -> /oauth2/callback?code  -> the *site* exchanges the code (it has the
                                        secret), creates a Django session, sets
                                        the `sessionid` cookie.

We keep that `sessionid` (+ `csrftoken`) and authenticate API calls with it
(SessionAuthentication). httpx follows the cross-domain redirect chain for us; we
only have to submit the one HTML form ADFS shows.
"""
from __future__ import annotations

import html
import re

import httpx

from app.sport.errors import AuthError

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class SsoAuth:
    def __init__(
        self,
        sso_base: str,
        client_id: str,
        redirect_uri: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self._sso_base = sso_base.rstrip("/")
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._timeout = timeout
        # Derive the site URLs from the redirect_uri (…/oauth2/callback).
        self._site_root = redirect_uri.split("/oauth2/")[0]  # https://sport.innopolis.university
        self._login_url = f"{self._site_root}/oauth2/login"

    @property
    def site_root(self) -> str:
        return self._site_root

    async def login(self, username: str, password: str) -> dict[str, str]:
        """Return cookies {'sessionid': ..., 'csrftoken': ...}. Raises AuthError."""
        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True, headers={"User-Agent": _BROWSER_UA}
        ) as client:
            page = await client.get(self._login_url)
            if "<form" not in page.text.lower() or "password" not in page.text.lower():
                # Could be already-authed or an unexpected page.
                cookies = _extract_cookies(client)
                if "sessionid" in cookies:
                    return cookies
                raise AuthError(f"no SSO login form (status {page.status_code}, url {page.url})")

            action_raw = _extract_form_action(page.text)
            action = str(page.url.join(action_raw)) if action_raw else str(page.url)
            form = _extract_hidden_inputs(page.text)
            form.update(
                {"UserName": username, "Password": password, "AuthMethod": "FormsAuthentication"}
            )

            result = await client.post(action, data=form)
            cookies = _extract_cookies(client)
            if "sessionid" not in cookies:
                if "password" in result.text.lower() and "<form" in result.text.lower():
                    raise AuthError("неверный логин или пароль")
                raise AuthError(f"login finished without session (final url {result.url})")
            return cookies


def _extract_cookies(client: httpx.AsyncClient) -> dict[str, str]:
    out: dict[str, str] = {}
    for cookie in client.cookies.jar:
        if cookie.name in ("sessionid", "csrftoken") and cookie.value:
            out[cookie.name] = cookie.value
    return out


def _extract_form_action(page_html: str) -> str | None:
    m = re.search(r'<form[^>]*\baction="([^"]+)"', page_html, re.IGNORECASE)
    return html.unescape(m.group(1)) if m else None


def _extract_hidden_inputs(page_html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for m in re.finditer(r"<input[^>]*type=\"hidden\"[^>]*>", page_html, re.IGNORECASE):
        tag = m.group(0)
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
    return fields
