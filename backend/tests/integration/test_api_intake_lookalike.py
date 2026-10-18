"""POST /intake/lookalike (Puerta A) por la API, contra Postgres con RLS. datos.gov.co lo atiende un transporte falso."""
import json
import logging
import re
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

BACKEND = Path(__file__).resolve().parents[2]
EJEMPLO = json.loads((BACKEND / "tests" / "fixtures" / "intake" / "empresas_ejemplo.json").read_text())
JURIDICA = "SOCIEDADES POR ACCIONES SIMPLIFICADAS SAS"


def _fila(nit, razon, ciiu="4711", camara="04"):
    return {"nit": nit, "digito_verificacion": "1", "razon_social": razon, "cod_ciiu_act_econ_pri": ciiu,
            "codigo_camara": camara, "organizacion_juridica": JURIDICA, "estado_matricula": "ACTIVA"}


# clave = lo que va entre % % en el LIKE (nombre normalizado en mayúsculas)
RESPUESTAS = {
    "COMERCIALIZADORA ANDINA DE ALIMENTOS": [_fila("900000001", "COMERCIALIZADORA ANDINA DE ALIMENTOS SAS")],
    "DISTRIBUCIONES EL FARO": [_fila("900000002", "DISTRIBUCIONES EL FARO LTDA", camara="14")],
    "SUPERMERCADOS LA SABANA": [_fila("900000003", "SUPERMERCADOS LA SABANA SA")],
    "FERRETERIA Y PINTURAS DEL CENTRO": [_fila("900000004", "FERRETERIA Y PINTURAS DEL CENTRO SAS", ciiu="4752")],
    "INVERSIONES CAFETERA DEL VALLE": [_fila("900000005", "INVERSIONES CAFETERA DEL VALLE SAS", camara="14")],
    "DROGUERIAS SALUD PLUS": [_fila("900000006", "DROGUERIAS SALUD PLUS SAS"),
                              _fila("900000007", "DROGUERIAS SALUD PLUS DEL NORTE SAS")],  # 2 NIT: ambiguo
    "ALMACENES LOS CERROS": [_fila("900000008", "ALMACENES LOS CERROS SA")],
    # "COMERCIAL PACIFICO MAYORISTA", "TIENDAS MERCADO FACIL", "PANIFICADORA INDUSTRIAL DEL SUR": sin coincidencias
}
NO_RESUELTOS = ["Droguerías Salud Plus S.A.S.", "Comercial Pacífico Mayorista S.A.S.", "Tiendas Mercado Fácil S.A.S.",
                "Panificadora Industrial del Sur S.A.S."]


@pytest.fixture
def api(cliente):  # noqa: F811
    cliente.pedidas = []

    def responder(request):
        cliente.pedidas.append(request)
        asked = re.match(r"upper\(razon_social\) like '%(.*?)%' AND", request.url.params["$where"]).group(1)
        return httpx.Response(200, json=RESPUESTAS.get(asked.replace("''", "'"), []))

    cliente.app.state.transporte_http = httpx.MockTransport(responder)
    return cliente


def _post(api, quien, nombres=EJEMPLO, **extra):
    return api.post("/intake/lookalike", json={"nombres": nombres, **extra}, headers=_bearer(quien))


def _n(admin, sql, **p):
    with admin.connect() as c:
        return c.execute(text(sql), p).scalar()


def test_devuelve_sugerencia_explicacion_y_no_resueltos(api, usuarios):
    r = _post(api, usuarios["a"])
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["sugerencia"] == {"pais": "CO", "ciiu": "4711", "departamento": "11", "ciudad": None,
                                    "ingresos_min": None, "palabras_clave": [], "exclusiones": []}
    assert cuerpo["explicacion"] == {"ciiu": [["4711", 5], ["4752", 1]], "departamento": [["11", 4], ["25", 2]]}
    assert cuerpo["resueltos"] == 6
    assert cuerpo["no_resueltos"] == NO_RESUELTOS
    assert set(cuerpo) == {"sugerencia", "explicacion", "resueltos", "no_resueltos", "costo_usd"}


def test_escribe_costo_de_computo_por_request_con_fuente_intake(api, admin, usuarios):
    r = _post(api, usuarios["a"])
    assert len(api.pedidas) == 10
    with admin.connect() as c:
        filas = c.execute(text("SELECT tipo, fuente, lead_id, lote_id, tenant_id, unidades * costo_unitario "
                               "FROM costos WHERE tenant_id = :a"), {"a": usuarios["tenant_a"]}).all()
    assert len(filas) == 10
    assert {(f[0], f[1], f[2]) for f in filas} == {("socrata_descarga", "intake", None)}
    assert len({f[3] for f in filas}) == 1 and filas[0][3] is not None
    assert Decimal(r.json()["costo_usd"]) == sum(f[5] for f in filas)
    assert _n(admin, "SELECT count(*) FROM costos WHERE tenant_id = :b", b=usuarios["tenant_b"]) == 0


def test_nombres_repetidos_se_consultan_una_vez(api, usuarios):
    _post(api, usuarios["a"], EJEMPLO + [EJEMPLO[0].upper(), EJEMPLO[1]])
    assert len(api.pedidas) == 10


def test_no_crea_busquedas_ni_leads(api, admin, usuarios):
    _post(api, usuarios["a"])
    assert _n(admin, "SELECT count(*) FROM busquedas WHERE tenant_id = :a", a=usuarios["tenant_a"]) == 0
    assert _n(admin, "SELECT count(*) FROM leads WHERE tenant_id = :a", a=usuarios["tenant_a"]) == 0


def test_sin_token_es_401(api):
    assert api.post("/intake/lookalike", json={"nombres": EJEMPLO}).status_code == 401


@pytest.mark.parametrize("cuantos", [4, 51])
def test_fuera_de_rango_es_422_con_codigo_y_sin_consultar(api, admin, usuarios, cuantos):
    r = _post(api, usuarios["a"], [f"Empresa Ficticia {i}" for i in range(cuantos)])
    assert r.status_code == 422
    assert r.json() == {"errores": [{"campo": "nombres", "codigo": "fuera_de_rango"}]}
    assert api.pedidas == []


def test_tenant_en_el_body_es_422(api, usuarios):
    assert _post(api, usuarios["a"], tenant_id=str(usuarios["tenant_b"])).status_code == 422


def test_fuente_caida_es_503_con_codigo_y_deja_su_costo(api, admin, usuarios):
    api.app.state.transporte_http = httpx.MockTransport(lambda req: httpx.Response(503, json=[]))
    r = _post(api, usuarios["a"])
    assert (r.status_code, r.json()) == (503, {"detail": "fuente_no_disponible"})
    assert _n(admin, "SELECT count(*) FROM costos WHERE tenant_id = :a AND fuente = 'intake'", a=usuarios["tenant_a"]) == 1  # un intento: el plazo de búsqueda (composicion) no reintenta


def test_los_nombres_pegados_no_salen_en_ningun_log(api, usuarios, caplog):
    caplog.set_level(logging.DEBUG)
    _post(api, usuarios["a"])
    api.app.state.transporte_http = httpx.MockTransport(lambda req: httpx.Response(503, json=[]))
    _post(api, usuarios["a"])
    _post(api, usuarios["a"], EJEMPLO[:3])  # 422
    volcado = "\n".join(f"{r.getMessage()} {r.exc_text or ''} {r.args}" for r in caplog.records).lower()
    assert caplog.records  # el captor funciona: sin esto el assert de abajo sería vacío
    for nombre in EJEMPLO:
        assert nombre.lower() not in volcado
        assert nombre.split()[0].lower() + " " + nombre.split()[1].lower() not in volcado
