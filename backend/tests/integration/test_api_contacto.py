"""API del primer toque (007): sin SMTP configurado es 503 con código; respuesta y tasa sin cruzar tenants."""
from uuid import uuid4

from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401


def test_sin_smtp_la_vista_previa_y_el_envio_son_503_con_codigo(cliente, usuarios, monkeypatch):
    for v in ("SMTP_HOST", "SMTP_USUARIO", "SMTP_CLAVE", "REMITENTE", "BAJA_SECRET", "API_BASE_URL", "URL_PRIVACIDAD"):
        monkeypatch.delenv(v, raising=False)
    h = _bearer(usuarios["a"])

    for ruta in (f"/busquedas/{uuid4()}/envio/vista-previa", f"/busquedas/{uuid4()}/envio"):
        r = cliente.post(ruta, headers=h)
        assert (r.status_code, r.json()) == (503, {"detail": "email_no_configurado"})


def test_respondio_de_un_contacto_inexistente_es_404(cliente, usuarios):
    r = cliente.post(f"/contactos/{uuid4()}/respondio", headers=_bearer(usuarios["a"]))
    assert (r.status_code, r.json()) == (404, {"detail": "sin_envio"})


def test_tasa_sin_contactos_es_lista_vacia(cliente, usuarios):
    r = cliente.get("/contactos/tasa", headers=_bearer(usuarios["a"]))
    assert (r.status_code, r.json()) == (200, {"items": []})


def test_sin_sesion_es_401(cliente):
    assert cliente.get("/contactos/tasa").status_code == 401
