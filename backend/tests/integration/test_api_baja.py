"""Baja por enlace, one-click y CLI (spec 007 §5, Fase 6). Se siembra como postgres; la API y la CLI actúan como app_rt."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import cli
from app.modulos.contacto.dominio.tokens import firmar
from app.modulos.contacto.infraestructura.repositorio_contactos import RepositorioContactosPostgres
from tests.integration.conftest import _url
from tests.integration.test_auth import _app, entorno  # noqa: F401  (fixture)
from tests.integration.test_envio_email import DESTINOS, _caso, _estados, _lead, busqueda, smtp  # noqa: F401

CLAVE = "s" * 32
ONE_CLICK = {"content": "List-Unsubscribe=One-Click", "headers": {"Content-Type": "application/x-www-form-urlencoded"}}


@pytest.fixture
def cliente(entorno):  # noqa: F811
    entorno.setenv("BAJA_SECRET", CLAVE)
    with TestClient(_app()) as c:
        yield c


@pytest.fixture
def contacto(admin, tenants, busqueda):  # noqa: F811
    """Un lead jurídico de A con su contacto aprobado; devuelve (tenant, lead, contacto)."""
    t, cid = tenants["a"], uuid4()
    lead = _lead(admin, t, 0).lead_id
    with admin.begin() as c:
        c.execute(text("INSERT INTO contactos (id, tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo) "
                       "VALUES (:c, :t, :l, :b, 'email', 'a', 'c')"), {"c": cid, "t": t, "l": lead, "b": busqueda})
    return t, lead, cid


def _token(contacto, proposito="baja", clave=CLAVE):
    t, _, cid = contacto
    return firmar(clave.encode(), proposito, t, cid)


def _cumplimiento(admin, lead):
    with admin.connect() as c:
        return c.execute(text("SELECT opt_out_at, solicitudes FROM cumplimiento WHERE lead_id = :l"), {"l": lead}).one()


def _bloqueos(admin, lead):
    with admin.connect() as c:
        return c.execute(text("SELECT bloqueo FROM contactos WHERE lead_id = :l"), {"l": lead}).scalars().all()


# T050
def test_get_muestra_confirmacion_y_no_da_de_baja(cliente, admin, contacto):
    token = _token(contacto)
    r = cliente.get(f"/baja/{token}")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert 'method="post"' in r.text and f'action="/baja/{token}"' in r.text
    assert tuple(_cumplimiento(admin, contacto[1])) == (None, [])
    assert _bloqueos(admin, contacto[1]) == [False]


def test_post_da_de_baja_y_es_idempotente(cliente, admin, contacto):
    token = _token(contacto)
    assert [cliente.post(f"/baja/{token}").status_code for _ in range(2)] == [200, 200]
    opt_out, solicitudes = _cumplimiento(admin, contacto[1])
    assert opt_out is not None
    assert [(s["tipo"], s["via"]) for s in solicitudes] == [("baja", "enlace")] * 2
    assert _bloqueos(admin, contacto[1]) == [True]


def test_one_click_rfc8058_sin_sesion(cliente, admin, contacto):
    r = cliente.post(f"/baja/{_token(contacto)}", **ONE_CLICK)
    assert r.status_code == 200
    assert _cumplimiento(admin, contacto[1]).opt_out_at is not None


def test_token_invalido_404_generico(cliente, admin, contacto):
    bueno = _token(contacto)
    alterado = bueno[:-2] + ("AA" if bueno[-2:] != "AA" else "BB")
    invalidos = [alterado, _token(contacto, "msgid"), _token(contacto, clave="x" * 32), "basura"]
    respuestas = [(r.status_code, r.text) for tok in invalidos
                  for r in (cliente.get(f"/baja/{tok}"), cliente.post(f"/baja/{tok}", **ONE_CLICK))]
    assert respuestas == [(404, '{"detail":"Not Found"}')] * len(respuestas)
    assert _cumplimiento(admin, contacto[1]).opt_out_at is None


def test_baja_no_expone_el_email(cliente, contacto):
    token = _token(contacto)
    respuestas = [cliente.get(f"/baja/{token}"), cliente.post(f"/baja/{token}")]
    assert [r.status_code for r in respuestas] == [200, 200]
    assert not any(DESTINOS[0] in r.text or str(contacto[1]) in r.text for r in respuestas)


def test_baja_sin_baja_secret_es_404(entorno, contacto):  # noqa: F811
    entorno.delenv("BAJA_SECRET", raising=False)
    with TestClient(_app()) as c:
        r = c.post(f"/baja/{_token(contacto)}")
    assert (r.status_code, r.text) == (404, '{"detail":"Not Found"}')


# T051
def test_opt_out_es_monotonico(cliente, admin, contacto):
    with admin.begin() as c:
        c.execute(text("UPDATE cumplimiento SET opt_out_at = '2026-01-01T00:00:00Z' WHERE lead_id = :l"),
                  {"l": contacto[1]})
    token = _token(contacto)
    cliente.post(f"/baja/{token}")
    cliente.post(f"/baja/{token}")
    opt_out, solicitudes = _cumplimiento(admin, contacto[1])
    assert opt_out.isoformat().startswith("2026-01-01")
    assert len(solicitudes) == 2


# T052 (desvío: `canal` solo admite 'email' y LeadsContactablesPostgres solo sirve email. El cierre de todos los
# canales se prueba por el opt-out del lead, que es lo que mira la elegibilidad SQL de cualquier canal).
def test_baja_cierra_todos_los_canales(cliente, rt, admin, contacto):
    t, lead, _ = contacto
    cliente.post(f"/baja/{_token(contacto)}")
    with admin.connect() as c:
        en_vista = c.execute(text("SELECT lead_id FROM v_leads_con_opt_out WHERE lead_id = :l"), {"l": lead}).all()
        otra = uuid4()
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:b, :t, 'CO', '{}')"),
                  {"b": otra, "t": t})
        c.commit()
    assert en_vista == [(lead,)]
    assert _bloqueos(admin, lead) == [True]
    assert RepositorioContactosPostgres(rt, t).crear(otra, uuid4(), lead, "a", "c") is False


def test_baja_descarta_el_aprobado(cliente, admin, contacto, busqueda):  # noqa: F811
    cliente.post(f"/baja/{_token(contacto)}")
    assert _estados(admin, busqueda) == {contacto[1]: "descartado"}


# T053
class _BajaAlReclamar:
    """Delega en el repo real y, apenas reclama, da de baja: vigente() tiene que frenar el envío."""

    def __init__(self, repo):
        self._repo = repo

    def __getattr__(self, nombre):
        return getattr(self._repo, nombre)

    def reclamar(self, contacto_id):
        ok = self._repo.reclamar(contacto_id)
        self._repo.dar_de_baja(contacto_id, "enlace")
        return ok


def test_baja_entre_reclamo_y_envio_gana(rt, admin, tenants, busqueda, smtp):  # noqa: F811
    t = tenants["a"]
    lead = _lead(admin, t, 0)
    caso = _caso(rt, t, [lead], smtp, repo=_BajaAlReclamar(RepositorioContactosPostgres(rt, t)))
    caso.vista_previa(busqueda)
    assert caso.enviar(busqueda) == 0
    assert smtp.mensajes == []
    assert _estados(admin, busqueda) == {lead.lead_id: "descartado"}


# T055: baja manual por CLI
def test_cli_baja_humano(monkeypatch, admin, contacto, capsys):
    t, lead, cid = contacto
    monkeypatch.setenv("DATABASE_URL", _url("TEST_DATABASE_URL"))
    assert cli.main(["baja", "--tenant", str(t), "--contacto", str(cid)]) == 0
    opt_out, solicitudes = _cumplimiento(admin, lead)
    assert opt_out is not None and [s["via"] for s in solicitudes] == ["humano"]
    assert "baja: 1" in capsys.readouterr().out


def test_cli_baja_de_otro_tenant_no_hace_nada(monkeypatch, admin, tenants, contacto, capsys):
    _, lead, cid = contacto
    monkeypatch.setenv("DATABASE_URL", _url("TEST_DATABASE_URL"))
    assert cli.main(["baja", "--tenant", str(tenants["b"]), "--contacto", str(cid)]) == 1
    assert _cumplimiento(admin, lead).opt_out_at is None
