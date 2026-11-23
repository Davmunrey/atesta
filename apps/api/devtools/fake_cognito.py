"""Local stand-in for Cognito managed login (local-dev-auth spec). Developer machines only.

Run: uv run python apps/api/devtools/fake_cognito.py  (listens on http://localhost:9000)
Then start the API with ATESTA_COGNITO_ISSUER and ATESTA_COGNITO_BASE_URL set to that URL.
"""

import base64
import hashlib
import html
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

KID = "local-dev"
_SUB_NAMESPACE = uuid.UUID("6f1a8a3e-1b3c-4c2e-9d55-2f0e6f7c9a10")


@dataclass
class _Grant:
    email: str
    nonce: str
    redirect_uri: str
    challenge: str
    expires: float


def create_app(issuer: str, client_id: str) -> FastAPI:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    codes: dict[str, _Grant] = {}
    refresh_tokens: dict[str, str] = {}
    app = FastAPI(title="Fake Cognito (local only)")

    def sign(claims: dict[str, Any]) -> str:
        now = int(time.time())
        body = {"iss": issuer, "iat": now, "exp": now + 1800, **claims}
        return jwt.encode(body, key, algorithm="RS256", headers={"kid": KID})

    def tokens_for(email: str, nonce: str | None) -> dict[str, Any]:
        sub = str(uuid.uuid5(_SUB_NAMESPACE, email))
        out: dict[str, Any] = {
            "access_token": sign(
                {"sub": sub, "token_use": "access", "client_id": client_id, "scope": "openid email"}
            ),
            "token_type": "Bearer",
            "expires_in": 1800,
        }
        if nonce is not None:
            out["id_token"] = sign(
                {
                    "sub": sub,
                    "aud": client_id,
                    "token_use": "id",
                    "nonce": nonce,
                    "email": email,
                    "email_verified": True,
                }
            )
            refresh = secrets.token_urlsafe(32)
            refresh_tokens[refresh] = email
            out["refresh_token"] = refresh
        return out

    @app.get("/.well-known/jwks.json")
    def jwks() -> dict[str, Any]:
        return {"keys": [{**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}

    @app.get("/oauth2/authorize", response_class=HTMLResponse)
    def authorize(
        client_id: str,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        code_challenge_method: str,
        lang: str = "es",
    ) -> str:
        if client_id != app.state.client_id or code_challenge_method != "S256":
            raise HTTPException(400, "invalid_request")
        hidden = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
        }
        fields = "".join(
            f'<input type="hidden" name="{k}" value="{html.escape(v)}">' for k, v in hidden.items()
        )
        label = "Código de 6 dígitos" if lang == "es" else "6-digit code"
        return (
            "<!doctype html><title>Fake Cognito</title><h1>Fake Cognito (local)</h1>"
            f'<form method="post" action="/login">{fields}'
            '<label>Email <input name="email" type="email" required></label>'
            f'<label>{label} <input name="code" pattern="[0-9]{{6}}" required></label>'
            "<button>Sign in</button></form>"
        )

    @app.post("/login")
    def login(
        client_id: Annotated[str, Form()],
        redirect_uri: Annotated[str, Form()],
        state: Annotated[str, Form()],
        nonce: Annotated[str, Form()],
        code_challenge: Annotated[str, Form()],
        email: Annotated[str, Form()],
        code: Annotated[str, Form()],
    ) -> RedirectResponse:
        if client_id != app.state.client_id or len(code) != 6 or not code.isdigit():
            raise HTTPException(400, "invalid_request")
        grant = secrets.token_urlsafe(24)
        codes[grant] = _Grant(
            email.strip().lower(), nonce, redirect_uri, code_challenge, time.time() + 300
        )
        return RedirectResponse(f"{redirect_uri}?{urlencode({'code': grant, 'state': state})}", 302)

    @app.post("/oauth2/token")
    def token(
        grant_type: Annotated[str, Form()],
        client_id: Annotated[str, Form()],
        code: Annotated[str | None, Form()] = None,
        redirect_uri: Annotated[str | None, Form()] = None,
        code_verifier: Annotated[str | None, Form()] = None,
        refresh_token: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        invalid = JSONResponse({"error": "invalid_grant"}, status_code=400)
        if client_id != app.state.client_id:
            return invalid
        if grant_type == "refresh_token":
            email = refresh_tokens.get(refresh_token or "")
            return invalid if email is None else JSONResponse(tokens_for(email, None))
        grant = codes.pop(code or "", None)
        if grant is None or grant.expires < time.time() or grant.redirect_uri != redirect_uri:
            return invalid
        digest = hashlib.sha256((code_verifier or "").encode()).digest()
        if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != grant.challenge:
            return invalid
        return JSONResponse(tokens_for(grant.email, grant.nonce))

    @app.post("/oauth2/revoke")
    def revoke(token: Annotated[str, Form()], client_id: Annotated[str, Form()]) -> JSONResponse:
        """Like Cognito: an unknown or already revoked token still gets 200."""
        if client_id != app.state.client_id:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        refresh_tokens.pop(token, None)
        return JSONResponse({})

    @app.get("/oauth2/userInfo")
    def userinfo(authorization: Annotated[str, Header()]) -> dict[str, str]:
        try:
            claims = jwt.decode(
                authorization.removeprefix("Bearer "),
                key.public_key(),
                algorithms=["RS256"],
                issuer=issuer,
            )
        except jwt.PyJWTError:
            raise HTTPException(401, "invalid_token") from None
        email = next((e for e in refresh_tokens.values() if _sub(e) == claims["sub"]), "")
        return {"sub": claims["sub"], "email": email, "email_verified": "true"}

    @app.get("/logout")
    def logout(client_id: str, logout_uri: str) -> RedirectResponse:
        return RedirectResponse(logout_uri, 302)

    app.state.client_id = client_id
    return app


def _sub(email: str) -> str:
    return str(uuid.uuid5(_SUB_NAMESPACE, email))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app("http://localhost:9000", "local-web"), host="127.0.0.1", port=9000)
