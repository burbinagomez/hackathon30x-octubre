"""Respuestas a mano y tasa por canal (spec 007, Fase 7). Se siembra como postgres; la CLI actúa como app_rt."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import cli
from app.db import unidad_de_trabajo
from tests.integration.conftest import _url
from tests.integration.test_envio_email import _lead, busqueda  # noqa: F401  (fixture)


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _url("TEST_DATABASE_URL"))


def _contacto(admin, t, b, i, enviado):
    cid, lead = uuid4(), _lead(admin, t, i).lead_id
    with admin.begin() as c:
        c.execute(text("INSERT INTO contactos (id, tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo, estado, enviado_en) "
                       "VALUES (:c, :t, :l, :b, 'email', 'a', 'c', CASE WHEN :e THEN 'enviado' ELSE 'aprobado' END, "
                       "CASE WHEN :e THEN now() END)"), {"c": cid, "t": t, "l": lead, "b": b, "e": enviado})
    return cid


def _respondio_en(admin, cid):
    with admin.connect() as c:
        return c.execute(text("SELECT respondio_en FROM contactos WHERE id = :c"), {"c": cid}).scalar()


def _cli(*argv):
    return cli.main([str(a) for a in argv])


def test_marcar_respondio_es_idempotente(entorno, admin, tenants, busqueda, capsys):  # noqa: F811
    t = tenants["a"]
    cid = _contacto(admin, t, busqueda, 0, enviado=True)
    assert _cli("respondio", "--tenant", t, "--contacto", cid) == 0
    primero = _respondio_en(admin, cid)
    assert _cli("respondio", "--tenant", t, "--contacto", cid) == 0
    assert primero is not None and _respondio_en(admin, cid) == primero
    assert capsys.readouterr().out.count("respondio: 1") == 2


def test_no_se_marca_un_no_enviado(entorno, rt, admin, tenants, busqueda, capsys):  # noqa: F811
    t = tenants["a"]
    cid = _contacto(admin, t, busqueda, 0, enviado=False)
    assert _cli("respondio", "--tenant", t, "--contacto", cid) == 1
    assert _respondio_en(admin, cid) is None
    assert "no hay un envío de ese contacto en ese tenant" in capsys.readouterr().err
    with pytest.raises(IntegrityError), unidad_de_trabajo(rt, t) as c:
        c.execute(text("UPDATE contactos SET respondio_en = now() WHERE id = :c"), {"c": cid})


def test_no_se_marca_desde_otro_tenant(entorno, admin, tenants, busqueda):  # noqa: F811
    cid = _contacto(admin, tenants["a"], busqueda, 0, enviado=True)
    assert _cli("respondio", "--tenant", tenants["b"], "--contacto", cid) == 1
    assert _respondio_en(admin, cid) is None


def test_tasa_por_canal(entorno, admin, tenants, busqueda, capsys):  # noqa: F811
    t = tenants["a"]
    respondio, _ = (_contacto(admin, t, busqueda, i, enviado=True) for i in range(2))
    _contacto(admin, t, busqueda, 2, enviado=False)  # aprobado sin enviar: fuera del denominador
    _cli("respondio", "--tenant", t, "--contacto", respondio)
    capsys.readouterr()
    assert _cli("tasa-respuesta", "--tenant", t) == 0
    assert capsys.readouterr().out == "email: contactados=2 respondieron=1 tasa=0.5\n"
    assert _cli("tasa-respuesta", "--tenant", tenants["b"]) == 0
    assert capsys.readouterr().out == "sin contactos\n"


def test_tasa_sin_envios_es_sin_dato(entorno, admin, tenants, busqueda, capsys):  # noqa: F811
    t = tenants["a"]
    _contacto(admin, t, busqueda, 0, enviado=False)
    assert _cli("tasa-respuesta", "--tenant", t) == 0
    assert capsys.readouterr().out == "email: contactados=0 respondieron=0 tasa=sin dato\n"
