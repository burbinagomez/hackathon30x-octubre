"""EnviarABusqueda contra Postgres y el SMTP falso (spec 007, Fase 5). Se siembra como postgres y se envía como app_rt."""
import threading
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import cli
from app.modulos.contacto.aplicacion.envio import EnviarABusqueda
from app.modulos.contacto.dominio.errores import MensajeCambio, SinVistaPrevia
from app.modulos.contacto.dominio.modelos import LeadContactable
from app.modulos.contacto.infraestructura.repositorio_contactos import RepositorioContactosPostgres
from app.modulos.contacto.infraestructura.smtp_email import SmtpEmail
from tests.contratos.test_smtp_email import _ajustes
from tests.falsos import LeadsContactablesFalso, RegistroCostosFalso
from tests.smtp_falso import SmtpFalso

MENSAJE = "Somos una agencia de carga y movemos importaciones desde Asia. ¿Le interesa una cotización?"
DESTINOS = [f"compras{i}@ferreteria-sintetica.test" for i in range(30)]
BASE_LEGAL = "persona_juridica_canal_publicado"


@pytest.fixture
def busqueda(admin, tenants):
    b = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios, mensaje_base) "
                       "VALUES (:b, :t, 'CO', '{}', :m)"), {"b": b, "t": tenants["a"], "m": MENSAJE})
    return b


@pytest.fixture
def smtp():
    with SmtpFalso(rechazar=frozenset({DESTINOS[29]})) as falso:
        yield falso


def _lead(admin, t, i, tipo="juridica", cumplimiento=True, opt_out=False, origen="sitio_web"):
    lead = uuid4()
    with admin.begin() as c:
        if tipo == "juridica":
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) "
                           "VALUES (:l, :t, 'CO', 'x', 'juridica')"), {"l": lead, "t": t})
        else:
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre_cifrado, tipo_titular) "
                           "VALUES (:l, :t, 'CO', :n, :tipo)"), {"l": lead, "t": t, "n": b"\0" * 29, "tipo": tipo})
        if cumplimiento:
            c.execute(text("INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of, opt_out_at) "
                           "VALUES (:t, :l, 'sintetica', 'x', 'https://x.test', now(), "
                           "CASE WHEN :o THEN now() END)"), {"t": t, "l": lead, "o": opt_out})
    return LeadContactable(lead, origen, DESTINOS[i])


def entorno_email(falso, **extra):
    a = _ajustes(falso)
    return {"DATABASE_URL": a.database_url, "CIFRADO_KEY": a.cifrado_key.get_secret_value(),
            "SMTP_HOST": a.smtp_host, "SMTP_PORT": str(a.smtp_port), "SMTP_USUARIO": a.smtp_usuario,
            "SMTP_CLAVE": a.smtp_clave.get_secret_value(), "SMTP_SEGURIDAD": a.smtp_seguridad,
            "REMITENTE": a.remitente, "BAJA_SECRET": a.baja_secret.get_secret_value(),
            "API_BASE_URL": a.api_base_url, "URL_PRIVACIDAD": a.url_privacidad,
            "EMAIL_MODO": "prueba", "EMAIL_PRUEBA_DESTINOS": DESTINOS[0]} | extra


def _caso(rt, t, leads, falso, modo="real", destinos=(), repo=None, costos=None):
    return EnviarABusqueda(
        t, repo or RepositorioContactosPostgres(rt, t), LeadsContactablesFalso(leads),
        SmtpEmail(_ajustes(falso), costos if costos is not None else RegistroCostosFalso(), Decimal(0)),
        clave_baja=b"k" * 32, remitente="Ana Pérez", url_api="https://api.ejemplo.test",
        url_privacidad="https://agencia-sintetica.test/privacidad", modo=modo, destinos_prueba=list(destinos))


def _estados(admin, b):
    with admin.connect() as c:
        return dict(c.execute(text("SELECT lead_id, estado FROM contactos WHERE busqueda_id = :b"), {"b": b}).all())


def _enviados(falso):
    return sorted(d for m in falso.mensajes for d in m.destinos)


def _base_legal(admin, lead):
    with admin.connect() as c:
        return c.execute(text("SELECT base_legal FROM cumplimiento WHERE lead_id = :l"), {"l": lead}).scalar()


# T040
def test_aprobado_que_sigue_elegible_se_envia(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    lead = _lead(admin, t, 0)
    caso = _caso(rt, t, [lead], smtp)
    caso.vista_previa(busqueda)
    assert caso.enviar(busqueda) == 1
    assert _enviados(smtp) == [DESTINOS[0]]
    assert _estados(admin, busqueda) == {lead.lead_id: "enviado"}


def test_envio_setea_base_legal(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    lead = _lead(admin, t, 0)
    caso = _caso(rt, t, [lead], smtp)
    caso.vista_previa(busqueda)
    assert _base_legal(admin, lead.lead_id) is None
    caso.enviar(busqueda)
    assert _base_legal(admin, lead.lead_id) == BASE_LEGAL


# T041
class _BorraBaseLegal:
    """Delega en el repo real y, apenas reclama, borra la base legal: vigente() tiene que frenar el envío."""

    def __init__(self, repo, admin):
        self._repo, self._admin = repo, admin

    def __getattr__(self, nombre):
        return getattr(self._repo, nombre)

    def reclamar(self, contacto_id):
        ok = self._repo.reclamar(contacto_id)
        with self._admin.begin() as c:
            c.execute(text("UPDATE cumplimiento SET base_legal = NULL WHERE lead_id = "
                           "(SELECT lead_id FROM contactos WHERE id = :c)"), {"c": contacto_id})
        return ok


def test_sin_base_legal_no_envia(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    lead = _lead(admin, t, 0)
    caso = _caso(rt, t, [lead], smtp, repo=_BorraBaseLegal(RepositorioContactosPostgres(rt, t), admin))
    caso.vista_previa(busqueda)
    assert caso.enviar(busqueda) == 0
    assert smtp.mensajes == []
    assert _estados(admin, busqueda) == {lead.lead_id: "descartado"}


# T042
@pytest.mark.parametrize("tipo", ["natural", "desconocido"])
def test_persona_natural_no_se_envia(rt, admin, tenants, busqueda, smtp, tipo):
    t = tenants["a"]
    juridica, otra = _lead(admin, t, 0), _lead(admin, t, 1, tipo=tipo)
    caso = _caso(rt, t, [juridica, otra], smtp)
    assert caso.vista_previa(busqueda).aprobados == 1
    assert caso.enviar(busqueda) == 1
    assert _enviados(smtp) == [DESTINOS[0]]
    assert otra.lead_id not in _estados(admin, busqueda)


def test_sin_canal_publicado_no_se_envia(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    publicado, comprado = _lead(admin, t, 0), _lead(admin, t, 1, origen="base_comprada")
    caso = _caso(rt, t, [publicado, comprado], smtp)
    assert caso.vista_previa(busqueda).aprobados == 1
    caso.enviar(busqueda)
    assert _enviados(smtp) == [DESTINOS[0]]


# T043
class _EsperaAlOtro:
    """Los dos envíos leen los aprobados antes de que cualquiera reclame: la carrera es real."""

    def __init__(self, repo, barrera):
        self._repo, self._barrera = repo, barrera

    def __getattr__(self, nombre):
        return getattr(self._repo, nombre)

    def aprobados(self, busqueda_id):
        filas = self._repo.aprobados(busqueda_id)
        self._barrera.wait()
        return filas


def test_dos_envios_en_paralelo_mandan_uno(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    lead = _lead(admin, t, 0)
    _caso(rt, t, [lead], smtp).vista_previa(busqueda)
    barrera, enviados = threading.Barrier(2, timeout=10), []
    casos = [_caso(rt, t, [lead], smtp, repo=_EsperaAlOtro(RepositorioContactosPostgres(rt, t), barrera))
             for _ in range(2)]
    hilos = [threading.Thread(target=lambda c=c: enviados.append(c.enviar(busqueda))) for c in casos]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(15)
    assert sorted(enviados) == [0, 1]
    assert _enviados(smtp) == [DESTINOS[0]]


# T044
def test_costo_en_libro_por_envio(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    ok, rechazado = _lead(admin, t, 0), _lead(admin, t, 29)
    costos = RegistroCostosFalso()
    caso = _caso(rt, t, [ok, rechazado], smtp, costos=costos)
    caso.vista_previa(busqueda)
    assert caso.enviar(busqueda) == 1
    assert sorted(f.lead_id for f in costos.filas if f.tipo == "email_envio") == sorted([ok.lead_id, rechazado.lead_id])
    assert all(f.lote_id == busqueda for f in costos.filas)
    # El 550 es del transporte: el contacto vuelve a aprobado para la próxima corrida.
    assert _estados(admin, busqueda) == {ok.lead_id: "enviado", rechazado.lead_id: "aprobado"}


# T046
def test_enviar_sin_dry_run_falla(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    caso = _caso(rt, t, [_lead(admin, t, 0)], smtp)
    with pytest.raises(SinVistaPrevia):
        caso.enviar(busqueda)
    assert smtp.mensajes == [] and _estados(admin, busqueda) == {}


def test_lead_nuevo_despues_del_dry_run_no_sale(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    viejo = _lead(admin, t, 0)
    _caso(rt, t, [viejo], smtp).vista_previa(busqueda)
    nuevo = _lead(admin, t, 1)
    assert _caso(rt, t, [viejo, nuevo], smtp).enviar(busqueda) == 1
    assert _enviados(smtp) == [DESTINOS[0]]
    assert nuevo.lead_id not in _estados(admin, busqueda)


# T04A
def test_mensaje_base_cambiado_frena(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    lead = _lead(admin, t, 0)
    caso = _caso(rt, t, [lead], smtp)
    caso.vista_previa(busqueda)
    with admin.begin() as c:
        c.execute(text("UPDATE busquedas SET mensaje_base = 'Otro texto, sin preguntas.' WHERE id = :b"), {"b": busqueda})
    with pytest.raises(MensajeCambio):
        caso.enviar(busqueda)
    with pytest.raises(MensajeCambio):
        caso.vista_previa(busqueda)
    assert smtp.mensajes == []
    # Otro --dry-run --rehacer lo destraba, con el texto nuevo.
    caso.vista_previa(busqueda, rehacer=True)
    assert caso.enviar(busqueda) == 1
    assert b"Otro texto, sin preguntas." in smtp.mensajes[0].datos


# T047
def test_tope_20_por_corrida(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    leads = [_lead(admin, t, i) for i in range(25)]
    caso = _caso(rt, t, leads, smtp)
    assert caso.vista_previa(busqueda).a_enviar == 20
    assert caso.enviar(busqueda) == 20
    assert len(smtp.mensajes) == 20
    assert sorted(_estados(admin, busqueda).values()) == ["aprobado"] * 5 + ["enviado"] * 20


# T048
def test_modo_prueba_solo_destinos_de_prueba(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    leads = [_lead(admin, t, i) for i in range(3)]
    caso = _caso(rt, t, leads, smtp, modo="prueba", destinos=[DESTINOS[1].upper()])
    resumen = caso.vista_previa(busqueda)
    assert (resumen.modo, resumen.aprobados, resumen.a_enviar) == ("prueba", 3, 1)
    assert caso.enviar(busqueda) == 1
    assert _enviados(smtp) == [DESTINOS[1]]


def test_modo_prueba_lista_vacia_no_manda(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    caso = _caso(rt, t, [_lead(admin, t, i) for i in range(3)], smtp, modo="prueba")
    resumen = caso.vista_previa(busqueda)
    assert (resumen.aprobados, resumen.a_enviar) == (3, 0)
    assert caso.enviar(busqueda) == 0
    assert sorted(_estados(admin, busqueda).values()) == ["aprobado"] * 3
    assert smtp.mensajes == []


# T049
def test_sin_fila_de_cumplimiento_no_envia(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    con, sin = _lead(admin, t, 0), _lead(admin, t, 1, cumplimiento=False)
    caso = _caso(rt, t, [con, sin], smtp)
    assert caso.vista_previa(busqueda).aprobados == 1
    caso.enviar(busqueda)
    assert _enviados(smtp) == [DESTINOS[0]]


def test_con_opt_out_no_envia(rt, admin, tenants, busqueda, smtp):
    t = tenants["a"]
    antes, despues, sigue = _lead(admin, t, 0, opt_out=True), _lead(admin, t, 1), _lead(admin, t, 2)
    caso = _caso(rt, t, [antes, despues, sigue], smtp)
    assert caso.vista_previa(busqueda).aprobados == 2
    # BAJA entre el dry-run y el envío: el reclamo vuelve a mirar el opt-out.
    with admin.begin() as c:
        c.execute(text("UPDATE cumplimiento SET opt_out_at = now() WHERE lead_id = :l"), {"l": despues.lead_id})
    assert caso.enviar(busqueda) == 1
    assert _enviados(smtp) == [DESTINOS[2]]


# T04B
def test_dry_run_imprime_resumen_sin_direcciones(rt, admin, tenants, busqueda, smtp, capsys, monkeypatch):
    t = tenants["a"]
    leads = [_lead(admin, t, i) for i in range(3)]
    caso = _caso(rt, t, leads, smtp, modo="prueba", destinos=[DESTINOS[0]])
    for nombre, valor in entorno_email(smtp).items():
        monkeypatch.setenv(nombre, valor)
    salida = cli.main(["enviar", "--tenant", str(t), "--busqueda", str(busqueda), "--dry-run"],
                      armar_envio=lambda ajustes, tenant: caso)
    out, err = capsys.readouterr()
    assert salida == 0
    assert "aprobados: 3" in out and "a enviar: 1" in out and "modo: prueba" in out
    assert MENSAJE in out
    assert not any(d in out + err for d in DESTINOS)
    assert smtp.mensajes == []
