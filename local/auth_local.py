"""Auth local: imita lo mínimo de Supabase Auth que usa la app, con UN usuario definido en local/.env.

SOLO para el docker compose local. Firma tokens ES256 con una clave que nace en cada arranque (reiniciar = volver a
entrar) y publica su JWKS: la api los verifica igual que en prod (aud, iss, exp, sub). Nunca se despliega.
Rutas: POST /auth/v1/token?grant_type=password|refresh_token, GET /auth/v1/user, POST /auth/v1/logout,
GET /auth/v1/.well-known/jwks.json.
"""
import hmac
import json
import os
import secrets
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

EMAIL = os.environ["LOCAL_EMAIL"].strip().lower()
CLAVE = os.environ["LOCAL_PASSWORD"]
USUARIO_ID = os.environ["LOCAL_AUTH_USER_ID"]
ISSUER = os.environ["LOCAL_AUTH_ISSUER"]
ORIGEN = os.environ.get("LOCAL_WEB_ORIGIN", "http://localhost:8080")
DURACION = 3600
KID = "local-" + secrets.token_hex(4)
PRIVADA = ec.generate_private_key(ec.SECP256R1())
JWK = {**json.loads(jwt.algorithms.ECAlgorithm.to_jwk(PRIVADA.public_key())), "kid": KID, "alg": "ES256", "use": "sig"}
REFRESCOS: set[str] = set()
USUARIO = {"id": USUARIO_ID, "aud": "authenticated", "role": "authenticated", "email": EMAIL,
           "app_metadata": {"provider": "email", "providers": ["email"]}, "user_metadata": {},
           "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}


def _sesion() -> dict:
    ahora = int(time.time())
    claims = {"sub": USUARIO_ID, "aud": "authenticated", "role": "authenticated", "iss": ISSUER, "email": EMAIL,
              "iat": ahora, "exp": ahora + DURACION, "session_id": str(uuid.uuid4())}
    refresco = secrets.token_urlsafe(32)
    REFRESCOS.add(refresco)
    return {"access_token": jwt.encode(claims, PRIVADA, algorithm="ES256", headers={"kid": KID}),
            "token_type": "bearer", "expires_in": DURACION, "expires_at": ahora + DURACION,
            "refresh_token": refresco, "user": USUARIO}


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *_):  # sin logs: no se imprimen cuerpos ni tokens
        pass

    def _responder(self, estado: int, cuerpo: dict | None = None):
        datos = b"" if cuerpo is None else json.dumps(cuerpo).encode()
        self.send_response(estado)
        self.send_header("Access-Control-Allow-Origin", ORIGEN)
        self.send_header("Access-Control-Allow-Headers", "authorization, apikey, content-type, x-client-info, x-supabase-api-version")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        if cuerpo is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _cuerpo(self) -> dict:
        largo = min(int(self.headers.get("Content-Length") or 0), 10_000)
        try:
            return json.loads(self.rfile.read(largo) or b"{}")
        except ValueError:
            return {}

    def do_OPTIONS(self):
        self._responder(204)

    def do_GET(self):
        ruta = urlsplit(self.path).path
        if ruta == "/auth/v1/.well-known/jwks.json":
            return self._responder(200, {"keys": [JWK]})
        if ruta == "/auth/v1/user":
            token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            try:
                jwt.decode(token, PRIVADA.public_key(), algorithms=["ES256"], audience="authenticated", issuer=ISSUER)
            except jwt.PyJWTError:
                return self._responder(401, {"code": 401, "msg": "invalid JWT"})
            return self._responder(200, USUARIO)
        if ruta == "/health":
            return self._responder(200, {"ok": True})
        self._responder(404, {"msg": "no encontrado"})

    def do_POST(self):
        partes = urlsplit(self.path)
        if partes.path == "/auth/v1/logout":
            return self._responder(204)
        if partes.path != "/auth/v1/token":
            return self._responder(404, {"msg": "no encontrado"})
        tipo = parse_qs(partes.query).get("grant_type", [""])[0]
        cuerpo = self._cuerpo()
        if tipo == "password":
            email_ok = hmac.compare_digest(str(cuerpo.get("email", "")).strip().lower().encode(), EMAIL.encode())
            clave_ok = hmac.compare_digest(str(cuerpo.get("password", "")).encode(), CLAVE.encode())
            if email_ok and clave_ok:
                return self._responder(200, _sesion())
        elif tipo == "refresh_token" and cuerpo.get("refresh_token") in REFRESCOS:
            REFRESCOS.discard(cuerpo["refresh_token"])
            return self._responder(200, _sesion())
        self._responder(400, {"error": "invalid_grant", "error_description": "Invalid login credentials",
                              "code": "invalid_credentials"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9999), Manejador).serve_forever()
