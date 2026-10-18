"""CLI `buscar` y `enriquecer`: sin red y sin Postgres. Los falsos viven en tests/, nunca en app/."""
import base64
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app import cli
from app.cli import Persistencia, _adaptadores_enriquecer, main
from app.composicion import cargar_tarifas
from app.config import Settings, SettingsEmail
from app.modulos.contacto.dominio.tokens import verificar
from app.modulos.descubrimiento.dominio.modelos import Actividad, EmpresaCruda, LeadParaEnriquecer, PaginaEmpresas
from app.modulos.enriquecimiento.dominio.puertos import ContactoPublicado
from app.modulos.enriquecimiento.infraestructura.adaptadores.jev_clasificador import JevClasificador
from tests.falsos import (EnriquecedorFalso, FuenteFalsa, RegistroCostosFalso, RepositorioLeadsFalso,
                          VerificadorFalso)

AS_OF = datetime(2026, 10, 1, tzinfo=UTC)
API_KEY = "clave-croma-falsa-9f3a"
DB_URL = "postgresql+psycopg://usuario:clave-db-falsa-7c1d@host.invalido:5432/base"
BUSCAR = ["buscar", "--tenant", str(uuid4()), "--pais", "CO", "--ciiu", "4711", "--departamento", "11"]


def _empresa(nit):
    return EmpresaCruda(pais="CO", nombre="ACME SAS", fuente="croma_supersociedades_co",
                        url_origen="https://croma.invalido/acme", as_of=AS_OF, actividad=Actividad("4711", "CIIU"),
                        id_fiscal=nit, tipo_titular="juridica")


class FuenteDelCLI(FuenteFalsa):
    """Acepta los kwargs del constructor que arma el CLI y devuelve 2 empresas con el mismo NIT."""

    def __init__(self, *, meta, registro_costos, lote_id, **kwargs):
        super().__init__(meta, registro_costos, lote_id, (_empresa("900.123.456-7"), _empresa("900123456")))


@pytest.fixture
def persistencia():
    return Persistencia(repo=RepositorioLeadsFalso(), costos=RegistroCostosFalso())


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setenv("CROMA_API_KEY", API_KEY)
    monkeypatch.setenv("DATABASE_URL", DB_URL)


def test_buscar_no_exige_auth_jwks_url_ni_auth_issuer(persistencia, entorno, monkeypatch, capsys):
    # AUTH_* son de la API; la CLI corre sin ellas (Settings compartido no las pide).
    monkeypatch.delenv("AUTH_JWKS_URL")
    monkeypatch.delenv("AUTH_ISSUER")
    try:
        codigo = main(BUSCAR, catalogo={"croma_supersociedades_co": FuenteDelCLI}, persistencia=persistencia)
    except Exception as error:  # una configuración inválida de AUTH no puede cortar la CLI
        codigo = f"{type(error).__name__} por configuración"
    assert codigo == 0
    assert "encontrados 2" in capsys.readouterr().out


def test_buscar_sin_tenant_falla(persistencia, capsys):
    codigo = main(["buscar", "--pais", "CO", "--ciiu", "4711"], catalogo={}, persistencia=persistencia)
    assert codigo != 0
    assert persistencia.repo.busquedas == {}


def test_buscar_imprime_resumen(persistencia, entorno, capsys):
    codigo = main(BUSCAR, catalogo={"croma_supersociedades_co": FuenteDelCLI}, persistencia=persistencia)
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "encontrados 2 · únicos 1 · nuevos 1 · créditos 1" in salida
    assert "sin_implementacion: datos_gov_co_rues, osm_overpass" in salida
    assert "sin_fuente_para" not in salida


def test_buscar_sin_adaptadores_reporta_sin_fuente_y_sin_implementacion(persistencia, monkeypatch, capsys):
    monkeypatch.delenv("CROMA_API_KEY", raising=False)
    codigo = main(BUSCAR, catalogo={}, persistencia=persistencia)
    salida = capsys.readouterr().out
    assert codigo == 0
    assert list(persistencia.repo.busquedas.values()) == ["terminada"]
    assert "sin_fuente_para: CO" in salida
    assert "sin_implementacion: croma_supersociedades_co, datos_gov_co_rues, osm_overpass" in salida
    assert persistencia.costos.filas == []
    assert persistencia.repo.leads == {}


def test_salida_no_contiene_secretos(persistencia, entorno, capsys):
    main(BUSCAR, catalogo={"croma_supersociedades_co": FuenteDelCLI}, persistencia=persistencia)
    captura = capsys.readouterr()
    salida = captura.out + captura.err
    assert salida
    assert API_KEY not in salida and "clave-db-falsa-7c1d" not in salida


def test_croma_sin_key_falla_sin_secretos(persistencia, monkeypatch, capsys):
    monkeypatch.delenv("CROMA_API_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    codigo = main(BUSCAR, catalogo={"croma_supersociedades_co": FuenteDelCLI}, persistencia=persistencia)
    captura = capsys.readouterr()
    assert codigo != 0
    assert "CROMA_API_KEY" in captura.err
    assert "clave-db-falsa-7c1d" not in captura.out + captura.err


def test_tarifa_croma_es_decimal_exacto(persistencia, entorno):
    recibidos = []

    class FuenteQueCaptura(FuenteDelCLI):
        def __init__(self, **kwargs):
            recibidos.append(kwargs.get("costo_unitario"))
            super().__init__(**kwargs)

    main(BUSCAR, catalogo={"croma_supersociedades_co": FuenteQueCaptura}, persistencia=persistencia)
    assert recibidos == [Decimal("0.00099")]
    assert isinstance(recibidos[0], Decimal)


def test_ciudad_llega_a_los_criterios(persistencia, entorno):
    recibidos = []

    class FuenteQueCaptura(FuenteDelCLI):
        def buscar(self, criterios, pagina):
            recibidos.append(criterios)
            return super().buscar(criterios, pagina)

    argv = ["buscar", "--tenant", str(uuid4()), "--pais", "CO", "--ciiu", "4711", "--ciudad", "Bogotá"]
    assert main(argv, catalogo={"osm_overpass": FuenteQueCaptura}, persistencia=persistencia) == 0
    assert [c.filtros["ciudad"] for c in recibidos] == ["Bogotá"]


class _GrabaKwargs:
    """Fuente que solo guarda los kwargs con los que la CLI la arma."""

    armadas: list[dict] = []

    def __init__(self, **kwargs):
        type(self).armadas.append(kwargs)
        self.meta = kwargs["meta"]

    def buscar(self, criterios, pagina):
        return PaginaEmpresas(empresas=(), total=None)


def test_datos_gov_co_recibe_url_y_token_de_settings(persistencia, entorno, monkeypatch, capsys):
    _GrabaKwargs.armadas = []
    monkeypatch.setenv("DATOS_GOV_CO_URL", "http://stub.local/resource/x.json")
    monkeypatch.setenv("DATOS_GOV_CO_APP_TOKEN", "tok-falso-123")

    main(BUSCAR, catalogo={"datos_gov_co_rues": _GrabaKwargs}, persistencia=persistencia)

    (kwargs,) = _GrabaKwargs.armadas
    assert kwargs.get("url") == "http://stub.local/resource/x.json"
    assert kwargs.get("app_token") == "tok-falso-123"
    assert "tok-falso-123" not in capsys.readouterr().out


def test_datos_gov_co_sin_variables_usa_los_defaults_del_adaptador(persistencia, entorno, monkeypatch):
    _GrabaKwargs.armadas = []
    monkeypatch.delenv("DATOS_GOV_CO_URL", raising=False)
    monkeypatch.delenv("DATOS_GOV_CO_APP_TOKEN", raising=False)

    main(BUSCAR, catalogo={"datos_gov_co_rues": _GrabaKwargs}, persistencia=persistencia)

    (kwargs,) = _GrabaKwargs.armadas
    assert "url" not in kwargs
    assert kwargs.get("app_token") is None


ENTORNO_EMAIL = {"DATABASE_URL": DB_URL, "SMTP_HOST": "smtp.invalido", "SMTP_USUARIO": "u",
                 "SMTP_CLAVE": "clave-smtp-falsa-4e2b", "REMITENTE": "Ana", "BAJA_SECRET": "b" * 32,
                 "API_BASE_URL": "https://api.invalido", "URL_PRIVACIDAD": "https://invalido/privacidad"}
ENVIAR = ["enviar", "--tenant", str(uuid4()), "--busqueda", str(uuid4())]


def _api_desplegada(clave, pedidos=None):
    """La API de Railway: GET /baja/<token> da 200 solo si el token lo firmó su propia BAJA_SECRET."""
    def responder(pedido):
        if pedidos is not None:
            pedidos.append(pedido.url)
        token = pedido.url.path.removeprefix("/baja/")
        return httpx.Response(200 if verificar(clave.encode(), "baja", token) else 404)
    return httpx.MockTransport(responder)


def _ajustes_email(monkeypatch, **extra):
    for nombre, valor in (ENTORNO_EMAIL | extra).items():
        monkeypatch.setenv(nombre, valor)
    return SettingsEmail()


def test_baja_responde_en_la_api_desplegada_con_la_misma_clave(monkeypatch):
    pedidos = []
    ajustes = _ajustes_email(monkeypatch)
    assert cli._hay_ruta_de_baja(ajustes, uuid4(), _api_desplegada("b" * 32, pedidos)) is True
    assert [u.host for u in pedidos] == ["api.invalido"]


def test_baja_con_otra_clave_en_la_api_no_vale(monkeypatch):
    ajustes = _ajustes_email(monkeypatch)
    assert cli._hay_ruta_de_baja(ajustes, uuid4(), _api_desplegada("x" * 32)) is False


def test_baja_con_la_api_caida_no_vale(monkeypatch):
    def caida(pedido):
        raise httpx.ConnectError("sin red", request=pedido)
    ajustes = _ajustes_email(monkeypatch)
    assert cli._hay_ruta_de_baja(ajustes, uuid4(), httpx.MockTransport(caida)) is False


def test_enviar_en_modo_prueba_no_consulta_la_api(monkeypatch):
    monkeypatch.setattr(cli, "_hay_ruta_de_baja", lambda *a: pytest.fail("en prueba no se consulta"))
    for nombre, valor in ENTORNO_EMAIL.items():
        monkeypatch.setenv(nombre, valor)
    assert main(ENVIAR, armar_envio=lambda ajustes, tenant: _SinAprobados()) == 1


class _SinAprobados:
    def enviar(self, busqueda_id):
        from app.modulos.contacto.dominio.errores import SinVistaPrevia
        raise SinVistaPrevia()


def test_enviar_en_modo_real_sin_ruta_de_baja_no_arma_nada(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_hay_ruta_de_baja", lambda *a: False)
    for nombre, valor in (ENTORNO_EMAIL | {"EMAIL_MODO": "real"}).items():
        monkeypatch.setenv(nombre, valor)
    armados = []
    codigo = main(ENVIAR, armar_envio=lambda ajustes, tenant: armados.append(tenant))
    assert codigo == 2 and armados == []
    assert "/baja" in capsys.readouterr().err


def test_enviar_con_configuracion_invalida_imprime_solo_nombres(monkeypatch, capsys):
    for nombre, valor in ENTORNO_EMAIL.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setenv("BAJA_SECRET", "corta-y-secreta")
    codigo = main(ENVIAR, armar_envio=lambda ajustes, tenant: pytest.fail("no se arma con config inválida"))
    err = capsys.readouterr().err
    assert codigo == 2 and "BAJA_SECRET" in err
    assert not any(v in err for v in ("corta-y-secreta", "clave-smtp-falsa-4e2b", "clave-db-falsa-7c1d"))


# --- enriquecer (T030) ---

TELEFONO = "+57 601 555 0101"
EMAIL = "ventas@andinos.invalid"


class RepoParaEnriquecer(RepositorioLeadsFalso):
    def __init__(self, leads):
        super().__init__()
        self.pendientes = list(leads)
        self.guardados = {}

    def sin_enriquecer(self, busqueda_id):
        return [lead for lead in self.pendientes if lead.id not in self.guardados]

    def guardar_enriquecimiento(self, lead_id, r):
        self.guardados[lead_id] = r


def _lead_con_web():
    return LeadParaEnriquecer(id=uuid4(), tipo_titular="juridica", nombre="Transportes Andinos", ciudad="Bogotá",
                              web="andinos.invalid", actividad="4923", descripcion_icp="transporte de carga", pais="CO")


def _enriquecer(persistencia, argv=None):
    def adaptadores(ajustes, costos, tarifas):
        sitio = {"andinos.invalid": ContactoPublicado((EMAIL,), ((TELEFONO, "sitio_web"),), "ok")}
        return VerificadorFalso(costos), EnriquecedorFalso(costos, sitio), None
    argv = argv or ["enriquecer", "--tenant", str(uuid4()), "--busqueda", str(uuid4())]
    return main(argv, persistencia=persistencia, adaptadores=adaptadores)


def test_enriquecer_imprime_solo_conteos_sin_contacto(entorno, capsys):
    persistencia = Persistencia(repo=RepoParaEnriquecer([_lead_con_web()]), costos=RegistroCostosFalso())
    codigo = _enriquecer(persistencia)
    captura = capsys.readouterr()
    salida = captura.out + captura.err
    assert codigo == 0
    assert "procesados 1 · contactables 1 · clasificados 0 · sin_clasificar 1 · cortado no" in captura.out
    assert TELEFONO not in salida and EMAIL not in salida and "andinos" not in salida.lower()
    assert len(persistencia.repo.guardados) == 1


def test_enriquecer_sin_tenant_falla(entorno, capsys):
    persistencia = Persistencia(repo=RepoParaEnriquecer([_lead_con_web()]), costos=RegistroCostosFalso())
    assert _enriquecer(persistencia, ["enriquecer", "--busqueda", str(uuid4())]) != 0
    assert persistencia.repo.guardados == {}


def test_sin_typesafe_api_key_no_hay_clasificador(entorno, monkeypatch):
    monkeypatch.setenv("CIFRADO_KEY", base64.b64encode(b"k" * 32).decode())
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_URL", "https://jev.invalido/clasificar")
    *_, clasificador = _adaptadores_enriquecer(Settings(), RegistroCostosFalso(), cargar_tarifas())
    assert clasificador is None


def test_con_typesafe_api_key_y_url_arma_jev(entorno, monkeypatch):
    monkeypatch.setenv("CIFRADO_KEY", base64.b64encode(b"k" * 32).decode())
    monkeypatch.setenv("TYPESAFE_API_KEY", "clave-jev-falsa-4b2e")
    monkeypatch.setenv("TYPESAFE_URL", "https://jev.invalido/clasificar")
    *_, clasificador = _adaptadores_enriquecer(Settings(), RegistroCostosFalso(), cargar_tarifas())
    assert isinstance(clasificador, JevClasificador)
    assert "clave-jev-falsa-4b2e" not in repr(vars(clasificador))


def test_verificador_bloqueado_no_asciende_a_juridica(entorno, monkeypatch):
    # P1 abierto: ascender sin consultar pasaría el nombre de una persona natural a claro.
    monkeypatch.setenv("CIFRADO_KEY", base64.b64encode(b"k" * 32).decode())
    verificador, *_ = _adaptadores_enriquecer(Settings(), RegistroCostosFalso(), cargar_tarifas())
    assert verificador.verificar(uuid4(), "doña rosa gomez", None, "CO").tipo_titular == "desconocido"
