"""`DatosGovCoRues.buscar_coincidencias` (Puerta A): por razón social, con transporte falso. Datos sintéticos."""
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.modulos.costos.dominio.modelos import ContextoCosto, OperacionCosto
from app.modulos.descubrimiento.aplicacion.camaras import cargar_camaras
from app.modulos.descubrimiento.dominio.errores import FuenteNoDisponible
from app.modulos.descubrimiento.dominio.modelos import MetaFuente
from app.modulos.descubrimiento.infraestructura.adaptadores.datos_gov_co_rues import DatosGovCoRues
from app.modulos.intake.dominio.puertos_lookalike import BuscadorRazonSocial

BACKEND = Path(__file__).resolve().parents[3]
CAMARAS = cargar_camaras(BACKEND / "config" / "camaras_co.yaml")
PERSONAS = ("representante_legal", "primer_nombre", "primer_apellido", "numero_identificacion",
            "num_identificacion_representante_legal")


def _fila(nit, razon="EMPRESA FICTICIA UNO SAS", ciiu="4711", camara="04", org="SOCIEDADES POR ACCIONES SIMPLIFICADAS SAS",
          estado="ACTIVA"):
    return {"nit": nit, "digito_verificacion": "1", "razon_social": razon, "cod_ciiu_act_econ_pri": ciiu,
            "codigo_camara": camara, "organizacion_juridica": org, "estado_matricula": estado,
            "fecha_renovacion": "20260410"}


class Costos:
    def __init__(self):
        self.filas: list[OperacionCosto] = []

    def registrar(self, op):
        self.filas.append(op)


def _adaptador(respuestas, costos=None):
    """`respuestas`: lista de (status, cuerpo) que se consumen en orden."""
    pedidas, restantes = [], list(respuestas)

    def responder(request):
        pedidas.append(request)
        estado, cuerpo = restantes.pop(0)
        return httpx.Response(estado, json=cuerpo)

    costos = costos if costos is not None else Costos()
    a = DatosGovCoRues(
        transporte=httpx.MockTransport(responder), reloj=lambda: datetime(2026, 10, 18, tzinfo=UTC),
        dormir=lambda s: None, costos=costos, cache=None, camaras=CAMARAS, tarifas={"computo_seg_usd": 0.000007},
        lote_id=None,
        meta=MetaFuente(clave="datos_gov_co_rues", proveedor="datos.gov.co", paises=frozenset({"CO"}),
                        filtros=frozenset({"ciiu", "departamento"}), trae=frozenset({"nit"}), tipo="dataset",
                        licencia="CC-BY-SA-4.0"),
    )
    return a, pedidas, costos


def test_devuelve_todas_las_coincidencias_juridicas_validas():
    ctx = ContextoCosto("intake", uuid4())
    filas = [_fila("900000001"), _fila("900000002", ciiu="4719", camara="14"),
             _fila("900000003", razon="OTRA FICTICIA SAS", camara="47"),
             _fila("1000000004", org="PERSONA NATURAL"),  # descartada: natural
             _fila("12345", razon="NIT MALO SAS")]  # descartada: NIT inválido
    a, _, _ = _adaptador([(200, filas)])
    r = a.buscar_coincidencias("empresa ficticia", ctx)
    assert [(c.nit, c.ciiu, c.camara, c.estado_matricula) for c in r] == [
        ("900000001", "4711", "04", "ACTIVA"), ("900000002", "4719", "14", "ACTIVA"),
        ("900000003", "4711", "47", "ACTIVA")]


def test_sin_filas_devuelve_lista_vacia():
    a, _, _ = _adaptador([(200, [])])
    assert list(a.buscar_coincidencias("nadie", ContextoCosto("intake", uuid4()))) == []


def test_registra_una_fila_de_computo_con_fuente_intake_y_lote_del_contexto():
    ctx = ContextoCosto("intake", uuid4())
    a, _, costos = _adaptador([(200, [_fila("900000001")])])
    a.buscar_coincidencias("empresa ficticia", ctx)
    assert len(costos.filas) == 1
    f = costos.filas[0]
    assert (f.tipo, f.fuente, f.lead_id, f.lote_id, f.gratis) == ("socrata_descarga", "intake", None, ctx.lote_id, False)
    assert f.costo_unitario == Decimal("0.000007") and f.proveedor == "datos.gov.co"


def test_cada_intento_http_deja_su_fila_aunque_la_fuente_falle():
    ctx = ContextoCosto("intake", uuid4())
    a, pedidas, costos = _adaptador([(503, []), (503, [])])
    with pytest.raises(FuenteNoDisponible):
        a.buscar_coincidencias("empresa ficticia", ctx)
    assert len(pedidas) == 2 and len(costos.filas) == 2
    assert {f.lote_id for f in costos.filas} == {ctx.lote_id} and {f.fuente for f in costos.filas} == {"intake"}


def test_el_costo_ya_esta_escrito_cuando_el_metodo_retorna():
    visto = []

    class CostosEspia(Costos):
        def registrar(self, op):
            super().registrar(op)
            visto.append(len(self.filas))

    a, _, costos = _adaptador([(200, [_fila("900000001")])], CostosEspia())
    r = a.buscar_coincidencias("empresa ficticia", ContextoCosto("intake", uuid4()))
    assert r and visto == [1] and len(costos.filas) == 1


def test_busca_por_razon_social_con_lista_blanca_de_columnas():
    a, pedidas, _ = _adaptador([(200, [])])
    a.buscar_coincidencias("empresa ficticia", ContextoCosto("intake", uuid4()))
    p = pedidas[0].url.params
    assert p["$where"] == (
        "upper(razon_social) like '%EMPRESA FICTICIA%'"
        " AND organizacion_juridica != 'PERSONA NATURAL' AND organizacion_juridica IS NOT NULL"
        " AND estado_matricula = 'ACTIVA' AND nit IS NOT NULL")
    columnas = p["$select"].split(",")
    assert "estado_matricula" in columnas and "nit" in columnas
    for prohibida in PERSONAS:
        assert prohibida not in p["$select"]


def test_el_nombre_va_escapado_en_el_soql():
    a, pedidas, _ = _adaptador([(200, [])] * 2)
    ctx = ContextoCosto("intake", uuid4())
    a.buscar_coincidencias("x' OR 1=1 --", ctx)
    where = pedidas[0].url.params["$where"]
    assert where.startswith("upper(razon_social) like '%X'' OR 1=1 --%' AND ")
    a.buscar_coincidencias("50%_off", ctx)  # comodines de LIKE: no entran
    assert pedidas[1].url.params["$where"].startswith("upper(razon_social) like '%50OFF%' AND ")


def test_nombre_vacio_o_solo_comodines_no_consulta():
    a, pedidas, costos = _adaptador([])
    assert list(a.buscar_coincidencias("%_", ContextoCosto("intake", uuid4()))) == []
    assert pedidas == [] and costos.filas == []


def test_cumple_buscador_razon_social():
    a, _, _ = _adaptador([])
    assert isinstance(a, BuscadorRazonSocial)


def test_contar_naturales_es_un_count_con_el_mismo_like_y_la_camara():
    a, pedidas, costos = _adaptador([(200, [{"count": "3"}])])
    ctx = ContextoCosto(None, None, uuid4())

    n = a.contar_naturales("juan perez", ["04", "58"], ctx)

    assert n == 3
    p = pedidas[0].url.params
    assert p["$select"] == "count(*)"
    assert "upper(razon_social) like '%JUAN PEREZ%'" in p["$where"]
    assert "organizacion_juridica = 'PERSONA NATURAL'" in p["$where"]
    assert "codigo_camara in('04','58')" in p["$where"]
    assert [(c.tipo, c.lead_id, c.lote_id) for c in costos.filas] == [("socrata_descarga", ctx.lead_id, None)]


@pytest.mark.parametrize("cuerpo", [[], [{"count": "no"}], [{"otra": "1"}], {"count": "1"}, [{"count": "-1"}]])
def test_contar_naturales_con_respuesta_ilegible_es_fuente_no_disponible(cuerpo):
    a, _, _ = _adaptador([(200, cuerpo)])

    with pytest.raises(FuenteNoDisponible):
        a.contar_naturales("juan perez", ["04"], ContextoCosto(None, None, uuid4()))


def test_contar_naturales_sin_camaras_o_con_comodines_no_consulta():
    a, pedidas, _ = _adaptador([(200, [{"count": "9"}])])
    ctx = ContextoCosto(None, None, uuid4())

    assert a.contar_naturales("juan perez", [], ctx) == 0
    assert a.contar_naturales("%_", ["04"], ctx) == 0
    assert pedidas == []


def test_contar_naturales_no_deja_pasar_codigos_de_camara_raros():
    a, pedidas, _ = _adaptador([(200, [{"count": "1"}])])

    a.contar_naturales("juan perez", ["04", "x' OR 1=1 --"], ContextoCosto(None, None, uuid4()))

    assert "codigo_camara in('04')" in pedidas[0].url.params["$where"] and "OR" not in pedidas[0].url.params["$where"]
