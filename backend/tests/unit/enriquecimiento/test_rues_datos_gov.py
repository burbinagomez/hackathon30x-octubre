"""RuesDatosGov (puerto VerificadorTitular): nombre + ciudad contra el RUES de datos.gov.co, enmienda 2026-10-18 de la 006.
Reusa el cliente de la 011 (`DatosGovCoRues`) con transporte falso: sin red. Datos sintéticos."""
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.modulos.descubrimiento.aplicacion.camaras import (
    alias_de_ciudad,
    cargar_camaras,
)
from app.modulos.descubrimiento.dominio.modelos import MetaFuente
from app.modulos.descubrimiento.infraestructura.adaptadores.datos_gov_co_rues import (
    LIMITE_COINCIDENCIAS,
    DatosGovCoRues,
)
from app.modulos.enriquecimiento.dominio.normalizar_titular import normalizar_ciudad
from app.modulos.enriquecimiento.infraestructura.adaptadores.rues_datos_gov import (
    RuesDatosGov,
)
from tests.falsos import RegistroCostosFalso

BACKEND = Path(__file__).resolve().parents[3]
CAMARAS = cargar_camaras(BACKEND / "config" / "camaras_co.yaml")
MUNICIPIOS = {c.codigo: c.municipio_sede for c in CAMARAS.values()}
SAS = "SOCIEDADES POR ACCIONES SIMPLIFICADAS SAS"
NOMBRE = "Transportes Andinos"  # lo que trae OSM: sin sufijo, con mayúsculas de uso


def _fila(nit="900111222", razon="TRANSPORTES ANDINOS S.A.S.", camara="04", estado="ACTIVA"):
    return {"nit": nit, "digito_verificacion": "1", "razon_social": razon, "cod_ciiu_act_econ_pri": "4923",
            "codigo_camara": camara, "organizacion_juridica": SAS, "estado_matricula": estado,
            "fecha_renovacion": "20260410"}


def _verificador(respuesta, intentos=2, naturales=0):
    """`respuesta`: lista de filas (200), o una función request -> Response / que lanza.
    `naturales`: lo que responde el conteo de personas naturales homónimas (request aparte, solo `count(*)`)."""
    pedidas = []

    def responder(request):
        pedidas.append(request)
        if callable(respuesta):
            return respuesta(request)
        if "count(" in request.url.params.get("$select", ""):
            return httpx.Response(200, json=[{"count": str(naturales)}])
        return httpx.Response(200, json=respuesta)

    costos = RegistroCostosFalso()
    cliente = DatosGovCoRues(
        transporte=httpx.MockTransport(responder), reloj=lambda: datetime(2026, 10, 18, tzinfo=UTC),
        dormir=lambda s: None, costos=costos, cache=None, camaras=CAMARAS, tarifas={"computo_seg_usd": Decimal("0.000007")},
        lote_id=None, intentos=intentos, timeout_seg=5.0,
        meta=MetaFuente(clave="datos_gov_co_rues", proveedor="datos.gov.co", paises=frozenset({"CO"}),
                        filtros=frozenset({"ciiu", "departamento"}), trae=frozenset({"nit"}), tipo="dataset",
                        licencia="CC-BY-SA-4.0"))
    return RuesDatosGov(cliente, MUNICIPIOS), pedidas, costos


def test_match_exacto_unico_en_la_misma_ciudad_es_juridica():
    v, _, _ = _verificador([_fila()])

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("juridica", "match_unico")
    c = r.constancia
    assert (c.motivo, c.fuente, c.dataset) == ("match_unico", "datos_gov_co_rues", "c82u-588k")
    assert (c.nit, c.razon_social, c.municipio_sede_camara) == ("900111222", "TRANSPORTES ANDINOS S.A.S.", "Bogotá")
    assert (c.codigo_camara, c.organizacion_juridica, c.estado_matricula) == ("04", SAS, "ACTIVA")


def test_el_nombre_y_la_ciudad_se_comparan_normalizados():
    v, _, _ = _verificador([_fila(razon="TRANSPORTES ANDINOS LTDA")])

    assert v.verificar(uuid4(), "  transportes   ANDÍNOS S.A.S. ", "BOGOTA D.C.", "CO").tipo_titular == "juridica"


def test_dos_nit_distintos_con_el_mismo_nombre_en_la_ciudad_es_desconocido():
    v, _, _ = _verificador([_fila("900111222"), _fila("900333444", razon="TRANSPORTES ANDINOS LTDA")])

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "ambiguo")
    assert r.constancia.candidatos == 2 and r.constancia.nit is None


def test_varias_matriculas_del_mismo_nit_son_un_solo_candidato():
    v, _, _ = _verificador([_fila("900111222"), _fila("900111222", razon="TRANSPORTES ANDINOS SAS")])

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "juridica"


def test_la_misma_razon_social_en_otra_ciudad_es_desconocido():
    v, _, _ = _verificador([_fila(camara="14")])  # cámara de Girardot

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "sin_match")
    assert r.constancia.nit is None  # sin match no se guarda a quién se parecía


def test_otra_empresa_con_el_mismo_nombre_en_otra_ciudad_no_vuelve_ambiguo_el_match():
    # La regla del dueño: "una sola empresa en la misma ciudad".
    v, _, _ = _verificador([_fila("900111222", camara="04"), _fila("900333444", camara="14")])

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.constancia.nit) == ("juridica", "900111222")


def test_una_camara_sin_municipio_conocido_nunca_matchea():
    v, _, _ = _verificador([_fila(camara="99")])

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "desconocido"


@pytest.mark.parametrize("ciudad", [None, "", "   "])
def test_sin_ciudad_es_desconocido_y_ni_siquiera_consulta(ciudad):
    v, pedidas, costos = _verificador([_fila()])

    r = v.verificar(uuid4(), NOMBRE, ciudad, "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "sin_ciudad")
    assert r.constancia.motivo == "sin_ciudad"
    assert pedidas == [] and costos.filas == []


def test_un_nombre_que_solo_es_sufijo_no_se_consulta():
    v, pedidas, _ = _verificador([_fila()])

    assert v.verificar(uuid4(), "S.A.S.", "Bogotá", "CO").tipo_titular == "desconocido"
    assert pedidas == []


def test_un_nombre_parecido_no_es_exacto():
    v, _, _ = _verificador([_fila(razon="TRANSPORTES ANDINOS DEL SUR SAS"), _fila("900333444", razon="ANDINOS")])

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "desconocido"


def test_si_la_respuesta_llega_al_tope_no_se_puede_afirmar_que_es_unica():
    filas = [_fila("9001%05d" % i, razon=f"TRANSPORTES ANDINOS {i} SAS") for i in range(LIMITE_COINCIDENCIAS - 1)]
    v, _, _ = _verificador(filas + [_fila()])  # exactamente el tope: pudo haber más sin traer

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "ambiguo")


def test_sin_resultados_es_desconocido():
    v, _, _ = _verificador([])

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").motivo == "sin_match"


def test_la_fuente_caida_es_desconocido_no_una_excepcion():
    v, _, _ = _verificador(lambda r: httpx.Response(503, json={}))

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "fuente_no_disponible")
    assert r.constancia.motivo == "fuente_no_disponible"


def test_el_timeout_es_desconocido():
    def tarda(request):
        raise httpx.ReadTimeout("lento", request=request)

    v, _, _ = _verificador(tarda)

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").motivo == "fuente_no_disponible"


def test_una_respuesta_ilegible_es_desconocido():
    v, _, _ = _verificador([{"nit": ["no", "es", "texto"]}, "basura"])

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "desconocido"


def test_cada_request_escribe_su_costo_con_el_lead_antes_de_devolver():
    v, pedidas, costos = _verificador([_fila()])
    lead = uuid4()

    v.verificar(lead, NOMBRE, "Bogotá", "CO")

    assert len(pedidas) == len(costos.filas) == 2  # la búsqueda por razón social y el conteo de naturales
    c = costos.filas[0]
    assert (c.tipo, c.proveedor, c.lead_id, c.lote_id, c.fuente) == ("socrata_descarga", "datos.gov.co", lead, None, None)
    assert c.costo_unitario == Decimal("0.000007") and c.unidades >= 0


def test_la_falla_tambien_cobra_cada_intento():
    v, pedidas, costos = _verificador(lambda r: httpx.Response(503, json={}), intentos=2)
    lead = uuid4()

    v.verificar(lead, NOMBRE, "Bogotá", "CO")

    assert len(pedidas) == len(costos.filas) == 2
    assert {c.lead_id for c in costos.filas} == {lead}


def test_la_consulta_lleva_el_nombre_normalizado_y_solo_campos_de_empresa():
    v, pedidas, _ = _verificador([_fila()])

    v.verificar(uuid4(), "Transportes Andínos S.A.S.", "Bogotá", "CO")

    params = pedidas[0].url.params
    assert "'%TRANSPORTES ANDINOS%'" in params["$where"]
    assert "representante" not in params["$select"] and "nombre" not in params["$select"].replace("razon_social", "")


@pytest.mark.parametrize("respuesta", [[_fila()], lambda r: httpx.Response(503, json={})])
def test_el_nombre_del_lead_no_sale_en_los_logs(caplog, respuesta):
    caplog.set_level(logging.DEBUG)
    v, _, _ = _verificador(respuesta)
    secreto = "Zxqvk Ficticia Andina"

    v.verificar(uuid4(), secreto, "Bogotá", "CO")

    texto = caplog.text.upper() + "".join(str(r.args) for r in caplog.records).upper()
    assert "ZXQVK" not in texto


def test_el_nombre_no_sale_en_el_mensaje_de_error_interno(caplog):
    # La excepción de la fuente lleva solo la clave y el status; lo que sube no incluye el nombre.
    v, _, _ = _verificador(lambda r: httpx.Response(500, json={"error": "Zxqvk"}))
    caplog.set_level(logging.DEBUG)

    v.verificar(uuid4(), "Zxqvk Ficticia", "Bogotá", "CO")

    assert "ZXQVK" not in caplog.text.upper()


def test_una_persona_natural_homonima_en_la_camara_vuelve_ambiguo_el_match():
    # "Juan Pérez" (OSM) y "JUAN PEREZ SAS": si existe la natural matriculada en la misma cámara, no hay certeza.
    v, pedidas, _ = _verificador([_fila(razon="JUAN PEREZ SAS")], naturales=1)

    r = v.verificar(uuid4(), "Juan Pérez", "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "ambiguo")
    assert r.constancia.naturales_homonimas == 1 and r.constancia.nit is None


def test_sin_naturales_homonimas_el_match_unico_sigue_siendo_juridica():
    v, _, _ = _verificador([_fila(razon="JUAN PEREZ SAS")], naturales=0)

    assert v.verificar(uuid4(), "Juan Pérez", "Bogotá", "CO").tipo_titular == "juridica"


def test_el_conteo_de_naturales_es_solo_un_count_filtrado_por_la_camara_de_la_ciudad():
    v, pedidas, _ = _verificador([_fila(razon="JUAN PEREZ SAS")])

    v.verificar(uuid4(), "Juan Pérez", "Bogotá", "CO")

    conteo = [p for p in pedidas if "count(" in p.url.params["$select"]]
    assert len(conteo) == 1
    p = conteo[0].url.params
    assert p["$select"] == "count(*)"  # ningún nombre de persona sale del servidor
    assert "'%JUAN PEREZ%'" in p["$where"] and "organizacion_juridica = 'PERSONA NATURAL'" in p["$where"]
    assert "codigo_camara in('04')" in p["$where"]


def test_el_conteo_de_naturales_tambien_cobra_su_request_con_el_lead():
    v, pedidas, costos = _verificador([_fila(razon="JUAN PEREZ SAS")])
    lead = uuid4()

    v.verificar(lead, "Juan Pérez", "Bogotá", "CO")

    assert len(pedidas) == len(costos.filas) == 2
    assert {c.lead_id for c in costos.filas} == {lead}


def test_sin_match_no_se_gasta_el_conteo_de_naturales():
    v, pedidas, _ = _verificador([_fila(camara="14")])

    v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert len(pedidas) == 1


def test_si_el_conteo_de_naturales_falla_es_desconocido():
    def falla_el_conteo(request):
        if "count(" in request.url.params.get("$select", ""):
            return httpx.Response(503, json={})
        return httpx.Response(200, json=[_fila()])

    v, _, _ = _verificador(falla_el_conteo)

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").motivo == "fuente_no_disponible"


@pytest.mark.parametrize("pais", ["MX", "PE", "BR", "", "co"])
def test_un_pais_que_no_es_co_es_desconocido_sin_request_ni_costo(pais):
    v, pedidas, costos = _verificador([_fila()])

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", pais)

    assert (r.tipo_titular, r.motivo) == ("desconocido", "pais_no_soportado")
    assert r.constancia.motivo == "pais_no_soportado"
    assert pedidas == [] and costos.filas == []


def test_el_tope_se_cuenta_sobre_las_filas_crudas_aunque_una_sea_invalida():
    # 100 filas del servidor, una con NIT malo que el cliente descarta: quedan 99 válidas, pero pudo haber más.
    filas = [_fila("9001%05d" % i, razon=f"TRANSPORTES ANDINOS {i} SAS") for i in range(LIMITE_COINCIDENCIAS - 2)]
    filas += [_fila(), _fila("12345", razon="NIT MALO SAS")]
    assert len(filas) == LIMITE_COINCIDENCIAS
    v, _, _ = _verificador(filas)

    r = v.verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "ambiguo")


def test_99_filas_crudas_no_son_truncadas():
    filas = [_fila("9001%05d" % i, razon=f"TRANSPORTES ANDINOS {i} SAS") for i in range(LIMITE_COINCIDENCIAS - 2)]
    v, _, _ = _verificador(filas + [_fila()])

    assert v.verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "juridica"


class _BuscadorFalso:
    """Un cliente del RUES que devuelve lo que se le diga, aunque el servidor real no lo mandaría."""

    def __init__(self, *filas, naturales=0):
        self.filas, self.naturales = filas, naturales

    def buscar_homonimas(self, nombre, contexto):
        return SimpleNamespace(coincidencias=list(self.filas), truncada=False)

    def contar_naturales(self, nombre, camaras, contexto):
        return self.naturales


def _coincidencia(nit="900111222", razon="TRANSPORTES ANDINOS SAS", camara="04", estado="ACTIVA", org=SAS):
    return SimpleNamespace(nit=nit, razon_social=razon, camara=camara, estado_matricula=estado, organizacion_juridica=org)


def _con(*filas):
    return RuesDatosGov(_BuscadorFalso(*filas), MUNICIPIOS)


def test_una_matricula_cancelada_no_cuenta_aunque_el_servidor_la_mande():
    r = _con(_coincidencia(estado="CANCELADA")).verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "sin_match")


@pytest.mark.parametrize("estado", [None, "", "SUSPENDIDA", "activa-no"])
def test_solo_la_matricula_activa_cuenta(estado):
    assert _con(_coincidencia(estado=estado)).verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "desconocido"


def test_una_activa_con_estado_en_minusculas_o_con_espacios_cuenta():
    assert _con(_coincidencia(estado=" activa ")).verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "juridica"


def test_una_fila_natural_colada_no_es_la_jurídica():
    r = _con(_coincidencia(org="PERSONA NATURAL")).verificar(uuid4(), NOMBRE, "Bogotá", "CO")

    assert r.tipo_titular == "desconocido"


def test_una_natural_colada_junto_a_la_sas_deja_ambiguo_y_no_sube():
    r = _con(_coincidencia(), _coincidencia(nit="1000000004", razon="TRANSPORTES ANDINOS", org="persona natural ")).verificar(
        uuid4(), NOMBRE, "Bogotá", "CO")

    assert (r.tipo_titular, r.motivo) == ("desconocido", "ambiguo")
    assert r.constancia.naturales_homonimas == 1 and r.constancia.nit is None


@pytest.mark.parametrize("org", [None, ""])
def test_sin_organizacion_juridica_no_se_afirma_que_es_juridica(org):
    assert _con(_coincidencia(org=org)).verificar(uuid4(), NOMBRE, "Bogotá", "CO").tipo_titular == "desconocido"


# --- Alias de ciudad: OSM trae "Cali", DIVIPOLA dice "Santiago de Cali" (T054) -------------------------------------

def test_el_nombre_corto_de_la_ciudad_coincide_con_la_sede_divipola():
    alias = alias_de_ciudad(CAMARAS, normalizar_ciudad)
    v = RuesDatosGov(_BuscadorFalso(_coincidencia(camara="08")), MUNICIPIOS, alias)

    r = v.verificar(uuid4(), NOMBRE, "Cali", "CO")

    assert (r.tipo_titular, r.motivo) == ("juridica", "match_unico")


def test_sin_alias_el_nombre_corto_no_coincide():
    r = _con(_coincidencia(camara="08")).verificar(uuid4(), NOMBRE, "Cali", "CO")

    assert r.tipo_titular == "desconocido"
