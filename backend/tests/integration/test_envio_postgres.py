"""Envío de punta a punta en EMAIL_MODO=prueba: leads de Postgres (0008), SMTP falso, costo, baja, respuesta y tasa."""
import email
import re
from email import policy
from uuid import uuid4

from sqlalchemy import text

from app import cli
from app.modulos.contacto.dominio.tokens import verificar
from app.modulos.contacto.infraestructura.leads_contactables import LeadsContactablesPostgres
from app.seguridad.cifrado import Cifrador
from tests.contratos.test_smtp_email import _ajustes
from tests.integration.conftest import _url
from tests.integration.test_envio_email import DESTINOS, MENSAJE, busqueda, entorno_email, smtp  # noqa: F401

CIFRADOR = Cifrador(_ajustes().cifrado_key.get_secret_value())


def _lead(admin, t, b, i, tipo="juridica", contactable=True, email=True, opt_out=False, canal="sitio_web"):
    """Lead de la búsqueda con el email cifrado como lo deja la 006."""
    lead = uuid4()
    blob = CIFRADOR.cifrar("email_cifrado", DESTINOS[i], t, lead) if email else None
    with admin.begin() as c:
        c.execute(text(
            "INSERT INTO leads (id, tenant_id, pais, nombre, nombre_cifrado, tipo_titular, contactable, email_cifrado, "
            "email_canal) VALUES (:l, :t, 'CO', CASE WHEN :j THEN 'x' END, CASE WHEN :j THEN NULL ELSE :n END, :tipo, "
            ":ct, :e, :ec)"), {"l": lead, "t": t, "j": tipo == "juridica", "n": b"\0" * 29, "tipo": tipo,
                               "ct": contactable, "e": blob, "ec": canal if email else None})
        c.execute(text("INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                       "VALUES (:t, :l, :b, 'sintetica', 'https://x.test', 'x')"), {"t": t, "l": lead, "b": b})
        c.execute(text("INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of, opt_out_at) "
                       "VALUES (:t, :l, 'sintetica', 'x', 'https://x.test', now(), CASE WHEN :o THEN now() END)"),
                  {"t": t, "l": lead, "o": opt_out})
    return lead


def test_solo_juridicas_contactables_con_email_y_sin_opt_out(rt, admin, tenants, busqueda):  # noqa: F811
    t = tenants["a"]
    buena = _lead(admin, t, busqueda, 0, canal="osm_contacto")
    for i, extra in enumerate([dict(tipo="natural"), dict(contactable=False), dict(email=False), dict(opt_out=True)], 1):
        _lead(admin, t, busqueda, i, **extra)
    leads = LeadsContactablesPostgres(rt, t, CIFRADOR).de_busqueda(busqueda, "email")
    assert [(x.lead_id, x.canal_origen, x.direccion) for x in leads] == [(buena, "osm_contacto", DESTINOS[0])]
    assert DESTINOS[0] not in repr(leads)
    assert LeadsContactablesPostgres(rt, t, CIFRADOR).de_busqueda(busqueda, "whatsapp") == []
    assert LeadsContactablesPostgres(rt, tenants["b"], CIFRADOR).de_busqueda(busqueda, "email") == []


def _cli(*argv):
    return cli.main([str(a) for a in argv])


def test_envio_de_punta_a_punta_en_modo_prueba(monkeypatch, admin, tenants, busqueda, smtp, capsys):  # noqa: F811
    t = tenants["a"]
    for nombre, valor in entorno_email(smtp, DATABASE_URL=_url("TEST_DATABASE_URL")).items():
        monkeypatch.setenv(nombre, valor)
    en_prueba, fuera = _lead(admin, t, busqueda, 0), _lead(admin, t, busqueda, 1)

    assert _cli("enviar", "--tenant", t, "--busqueda", busqueda, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "modo: prueba" in out and "aprobados: 2" in out and "a enviar: 1" in out and MENSAJE in out
    assert smtp.mensajes == []

    assert _cli("enviar", "--tenant", t, "--busqueda", busqueda) == 0
    out, err = capsys.readouterr()
    assert out == "enviados: 1\n" and not any(d in out + err for d in DESTINOS)
    assert [m.destinos for m in smtp.mensajes] == [[DESTINOS[0]]]

    with admin.connect() as c:
        estados = dict(c.execute(text("SELECT lead_id, estado FROM contactos WHERE busqueda_id = :b"), {"b": busqueda}).all())
        cid = c.execute(text("SELECT id FROM contactos WHERE lead_id = :l"), {"l": en_prueba}).scalar()
        costos = c.execute(text("SELECT tipo, canal, lead_id FROM costos WHERE tenant_id = :t AND fuente = 'smtp_email'"),
                           {"t": t}).all()
    assert estados == {en_prueba: "enviado", fuera: "aprobado"}
    assert [tuple(f) for f in costos] == [("email_envio", "email", en_prueba)]

    msg = email.message_from_bytes(smtp.mensajes[0].datos, policy=policy.default)
    token = re.search(r"https://api\.ejemplo\.test/baja/(\S+)", msg.get_content()).group(1)
    assert f"/baja/{token}>" in msg["List-Unsubscribe"]
    assert verificar(b"b" * 32, "baja", token) == (t, cid)

    assert _cli("respondio", "--tenant", t, "--contacto", cid) == 0
    capsys.readouterr()
    assert _cli("tasa-respuesta", "--tenant", t) == 0
    assert capsys.readouterr().out == "email: contactados=1 respondieron=1 tasa=1\n"
