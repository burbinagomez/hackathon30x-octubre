"""T031 [MIN]: Nueva búsqueda y Tablero por la API, contra Postgres con RLS y las fuentes reales con transporte falso.

Contrato que fija este archivo para el verde (T032):
- la raíz de composición lee `app.state.transporte_http` (un `httpx.BaseTransport`) y `app.state.actividades_yaml`
  (el contenido de config/actividades.yaml); el lifespan los deja con los valores de producción y los tests los pisan;
- vista previa: 201; ejecutar: 200; sin la búsqueda (o ajena): 404; ya no es borrador: 409; cuerpo inválido: 422;
- los errores y los motivos son códigos, nunca una frase.
Sin red: los dos hosts (Overpass y datos.gov.co) los atiende un MockTransport. Datos sintéticos.
"""
import json
from decimal import Decimal
import re
from decimal import Decimal
from types import SimpleNamespace
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text

# Los fixtures de auth (app real, JWKS local, usuarios de A y B) se reusan tal cual.
from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

BACKEND = Path(__file__).resolve().parents[2]
FILAS = json.loads((BACKEND / "tests" / "fixtures" / "datos_gov_co" / "filas.json").read_text())
OSM = json.loads((BACKEND / "tests" / "fixtures" / "osm" / "bogota_4711.json").read_text())
HEADER_AS_OF = "Fri, 02 Oct 2026 21:39:26 GMT"

PEDIDO = {
    "pais": "CO", "ciiu": "4711", "departamento": "11", "ciudad": "Bogotá",
    "palabras_clave": [], "exclusiones": [], "canal_preferido": "email",
    "tope_gasto_usd": 5, "mensaje_base": "Hola, somos una empresa de ejemplo.",
}
CODIGO = re.compile(r"^[a-z][a-z0-9_]*$")

# Geografía SINTÉTICA para los tests: el co.yaml real tiene las 33 divisiones y, hasta que alguien lo corra con red, ningún
# municipio. Tolima trae Ibagué (DIVIPOLA 73001).
TOLIMA = {"iso_3166_2": "CO-TOL", "codigo_nativo": "73", "nombre_es": "Tolima", "nombre_en": "Tolima",
          "municipios": [{"codigo_nativo": "73001", "nombre": "Ibagué"}, {"codigo_nativo": "73449", "nombre": "Melgar"}]}
BOGOTA = {"iso_3166_2": "CO-DC", "codigo_nativo": "11", "nombre_es": "Bogotá, D.C.", "nombre_en": "Bogotá, D.C.",
          "municipios": [{"codigo_nativo": "11001", "nombre": "Bogotá"}]}
GEOGRAFIA_DE_PRUEBA = {"CO": {"pais": "CO", "divisiones": [TOLIMA]}}
GEOGRAFIA_DEL_FLUJO = {"CO": {"pais": "CO", "divisiones": [BOGOTA, TOLIMA]}}




@pytest.fixture
def api(cliente):
    """El cliente de auth, con las fuentes atendidas por un transporte falso. `api.pedidas` lista cada request saliente."""
    api = cliente
    api.pedidas = []

    def responder(request):
        api.pedidas.append(request)
        if request.url.host == "www.datos.gov.co":
            return httpx.Response(200, json=FILAS, headers={"X-SODA2-Truth-Last-Modified": HEADER_AS_OF})
        return httpx.Response(200, json=OSM)

    api.app.state.transporte_http = httpx.MockTransport(responder)
    api.app.state.geografia = GEOGRAFIA_DEL_FLUJO  # la real no trae municipios hasta que alguien corra el script con red
    return api


@pytest.fixture
def api_real(cliente):
    """El cliente tal como arranca el lifespan: la geografía y las fuentes reales, sin pisar nada."""
    return cliente


def _vista_previa(api, quien, **cambios):
    return api.post("/busquedas/vista-previa", json={**PEDIDO, **cambios}, headers=_bearer(quien))


def _crear(api, quien, **cambios) -> str:
    """Crea un borrador y devuelve su id; si la API no responde 201, el assert lo dice (no un KeyError)."""
    r = _vista_previa(api, quien, **cambios)
    assert r.status_code == 201
    return r.json()["busqueda_id"]


def _tablero(api, quien) -> dict:
    r = api.get("/tablero/fuentes", headers=_bearer(quien))
    assert r.status_code == 200
    return r.json()


def _ejecutar(api, quien, busqueda_id):
    return api.post(f"/busquedas/{busqueda_id}/ejecutar", headers=_bearer(quien))


def _ejecutar_o_500(api, quien, busqueda_id):
    """Como _ejecutar, pero una excepción sin atrapar en la API se ve como un 500 (el TestClient la relanzaría)."""
    try:
        return _ejecutar(api, quien, busqueda_id)
    except Exception:  # noqa: BLE001
        return SimpleNamespace(status_code=500, json=lambda: {})


def _contar(admin, sql, **params):
    with admin.connect() as c:
        return c.execute(text(sql), params).scalar()


# --- el tenant sale del token, no del body --------------------------------------------------------------------

def test_tenant_sale_del_token_no_del_body(api, admin, usuarios):
    rechazada = _vista_previa(api, usuarios["a"], tenant_id=str(usuarios["tenant_b"]))
    assert rechazada.status_code == 422  # extra='forbid': el campo ni se ignora
    assert _contar(admin, "SELECT count(*) FROM busquedas WHERE tenant_id IN (:a, :b)",
                   a=usuarios["tenant_a"], b=usuarios["tenant_b"]) == 0

    creada = _vista_previa(api, usuarios["a"])

    assert creada.status_code == 201
    assert _contar(admin, "SELECT tenant_id FROM busquedas WHERE id = :id", id=creada.json()["busqueda_id"]) == usuarios["tenant_a"]


def test_tenant_b_no_ejecuta_busqueda_de_a_y_no_distingue_ajena_de_inexistente(api, admin, usuarios):
    busqueda_id = _crear(api, usuarios["a"])

    ajena = _ejecutar(api, usuarios["b"], busqueda_id)
    inexistente = _ejecutar(api, usuarios["b"], uuid4())

    assert ajena.status_code == 404  # nunca 409: B no se entera de que existe
    assert (inexistente.status_code, inexistente.json()) == (404, ajena.json())
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "borrador"
    assert api.pedidas == []  # nadie llamó a ninguna fuente
    assert _contar(admin, "SELECT count(*) FROM costos WHERE tenant_id IN (:a, :b)",
                   a=usuarios["tenant_a"], b=usuarios["tenant_b"]) == 0


def test_ejecutar_dos_veces_da_409_y_no_vuelve_a_llamar_ni_a_cobrar(api, admin, usuarios):
    busqueda_id = _crear(api, usuarios["a"])
    primera = _ejecutar(api, usuarios["a"], busqueda_id)
    pedidas = len(api.pedidas)
    filas_costo = _contar(admin, "SELECT count(*) FROM costos WHERE tenant_id = :a", a=usuarios["tenant_a"])

    segunda = _ejecutar(api, usuarios["a"], busqueda_id)

    assert primera.status_code == 200
    assert segunda.status_code == 409
    assert len(api.pedidas) == pedidas
    assert _contar(admin, "SELECT count(*) FROM costos WHERE tenant_id = :a", a=usuarios["tenant_a"]) == filas_costo
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "completada"


# --- tope de gasto (advisor, costos) --------------------------------------------------------------------------

def test_ejecutar_con_costo_maximo_sobre_tope_da_409(api, admin, usuarios):
    # OSM (0.00042) + datos.gov.co (0.00084) = 0.00126 de peor caso: el tope de 0.0001 no alcanza ni para una.
    r = _vista_previa(api, usuarios["a"], tope_gasto_usd="0.0001")
    assert r.status_code == 201
    assert r.json()["dentro_del_tope"] is False
    assert r.json()["costo_maximo_usd"] is not None and Decimal(r.json()["costo_maximo_usd"]) == Decimal("0.00126")
    busqueda_id = r.json()["busqueda_id"]
    filas_antes = _contar(admin, "SELECT count(*) FROM costos WHERE tenant_id = :a", a=usuarios["tenant_a"])

    ejecutada = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert ejecutada.status_code == 409
    assert ejecutada.json() == {"detail": "tope_excedido"}  # un código; distinto de "ya_ejecutada"
    assert api.pedidas == []  # 0 requests a las fuentes
    assert _contar(admin, "SELECT count(*) FROM costos WHERE tenant_id = :a", a=usuarios["tenant_a"]) == filas_antes
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "borrador"
    assert _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :a", a=usuarios["tenant_a"]) == 0


def test_tope_justo_para_el_costo_maximo_ejecuta(api, admin, usuarios):
    busqueda_id = _crear(api, usuarios["a"], tope_gasto_usd="0.00126")

    r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200 and r.json()["estado"] == "completada"
    assert len(api.pedidas) > 0


def _con_croma(api):
    """Lo que arma el lifespan cuando hay CROMA_API_KEY: Croma en el registro, la key en Settings y los límites del YAML."""
    from pydantic import SecretStr

    from app.composicion import registro_api
    from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo

    estado = api.app.state
    estado.settings = estado.settings.model_copy(update={"croma_api_key": SecretStr("clave-de-prueba")})
    estado.registro = registro_api(BACKEND / "config" / "fuentes.yaml", catalogo)
    estado.limites = yaml.safe_load((BACKEND / "config" / "fuentes.yaml").read_text())["limites"]
    previo = estado.transporte_http

    def responder(request):
        if request.url.host == "api.croma.run":
            api.pedidas.append(request)
            return httpx.Response(200, json={"total": 1, "data": [
                {"nit": "900.555.444-3", "name": "EMPRESA SINTETICA S.A.S.", "city": "BOGOTÁ", "ciiu_code": "4711"}]})
        return previo.handle_request(request)

    estado.transporte_http = httpx.MockTransport(responder)


def test_con_croma_el_tope_corta_antes_de_gastar_un_credito(api, admin, usuarios):
    _con_croma(api)
    r = _vista_previa(api, usuarios["a"], tope_gasto_usd="0.0013")  # OSM + datos.gov.co (0.00126) caben; con Croma (0.00225) no
    assert r.json()["dentro_del_tope"] is False and Decimal(r.json()["costo_maximo_usd"]) == Decimal("0.00225")

    ejecutada = _ejecutar_o_500(api, usuarios["a"], r.json()["busqueda_id"])

    assert (ejecutada.status_code, ejecutada.json()) == (409, {"detail": "tope_excedido"})
    assert api.pedidas == []
    assert _contar(admin, "SELECT count(*) FROM costos WHERE tenant_id = :a", a=usuarios["tenant_a"]) == 0


def test_con_croma_y_tope_suficiente_deja_fila_croma_consulta_del_lote_y_lead_juridico(api, admin, usuarios):
    _con_croma(api)
    busqueda_id = _crear(api, usuarios["a"])  # tope 5

    r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200
    assert _contar(admin, "SELECT count(*) FROM costos WHERE tenant_id = :a AND tipo = 'croma_consulta' AND proveedor = 'croma' "
                          "AND lote_id = :l AND unidades = 1", a=usuarios["tenant_a"], l=busqueda_id) == 1
    assert _contar(admin, "SELECT tipo_titular FROM leads WHERE tenant_id = :a AND id_fiscal = '900555444'",
                   a=usuarios["tenant_a"]) == "juridica"
    assert _contar(admin, "SELECT count(*) FROM cumplimiento WHERE tenant_id = :a AND fuente = 'croma_supersociedades_co' "
                          "AND licencia LIKE '%Croma%' AND url_origen LIKE '%?nit=900555444'", a=usuarios["tenant_a"]) == 1


# --- validación -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cambios, campo", [
    pytest.param({"ciiu": "471"}, "ciiu", id="ciiu_de_3_digitos"),
    pytest.param({"pais": "AR"}, "pais", id="pais_fuera_del_enum"),
    pytest.param({"tope_gasto_usd": 0}, "tope_gasto_usd", id="tope_cero"),
    pytest.param({"mensaje_base": "x" * 1001}, "mensaje_base", id="mensaje_de_1001_caracteres"),
    pytest.param({"palabras_clave": [f"p{i}" for i in range(11)]}, "palabras_clave", id="once_palabras_clave"),
    pytest.param({"palabras_clave": ["x" * 41]}, "palabras_clave", id="palabra_clave_de_41_caracteres"),
    pytest.param({"canal_preferido": "whatsapp"}, "canal_preferido", id="canal_deshabilitado_en_el_yaml"),
    pytest.param({"canal_preferido": "fax"}, "canal_preferido", id="canal_que_no_existe"),
])
def test_validacion(api, admin, usuarios, cambios, campo):
    r = _vista_previa(api, usuarios["a"], **cambios)

    assert r.status_code == 422
    errores = r.json()["errores"]
    assert campo in {e["campo"] for e in errores}
    assert all(set(e) == {"campo", "codigo"} and CODIGO.match(e["codigo"]) for e in errores)  # códigos, no frases
    assert _contar(admin, "SELECT count(*) FROM busquedas WHERE tenant_id = :a", a=usuarios["tenant_a"]) == 0


def test_validacion_ciiu_devuelve_el_nombre_de_la_regla(api, usuarios):
    r = _vista_previa(api, usuarios["a"], ciiu="471")
    assert r.status_code == 422
    assert {"campo": "ciiu", "codigo": "string_pattern_mismatch"} in r.json()["errores"]


# --- vista previa ---------------------------------------------------------------------------------------------

def test_vista_previa_devuelve_motivos_como_codigo(api, admin, usuarios):
    # 9999 no tiene mapeo a OSM; datos.gov.co filtra por ciiu y departamento, así que corre.
    r = _vista_previa(api, usuarios["a"], ciiu="9999")

    assert r.status_code == 201
    cuerpo = r.json()
    UUID(cuerpo["busqueda_id"])
    assert [f["fuente"] for f in cuerpo["fuentes"]] == ["datos_gov_co_rues"]
    assert cuerpo["descartadas"] == [{"fuente": "osm_overpass", "motivo": "sin_mapeo_actividad"}]
    # Sin `contar` (Pulido) no hay conteo ni estimado: null, nunca 0. El tope sí se aplica: costo máximo y veredicto.
    assert cuerpo["fuentes"][0] == {"fuente": "datos_gov_co_rues", "conteo": None, "motivo": "sin_conteo",
                                    "ignorados": ["ciudad"], "truncado": False}
    for clave in ("costo_vista_previa_usd", "costo_estimado_usd", "creditos_restantes_mes", "requests_restantes_24h"):
        assert cuerpo[clave] is None, clave
    assert cuerpo["costo_maximo_usd"] is not None
    assert Decimal(cuerpo["costo_maximo_usd"]) == Decimal("0.00084")  # solo datos.gov.co: 2 x 2 x 30 s x 0.0000070
    assert cuerpo["dentro_del_tope"] is True  # tope 5
    assert api.pedidas == []  # la vista previa del [MIN] no sale a ninguna fuente
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=cuerpo["busqueda_id"]) == "borrador"


# --- actividades ----------------------------------------------------------------------------------------------

def test_actividades_trae_ambos_nombres(api, usuarios):
    api.app.state.actividades_yaml = {
        "1081": {"nombre_es": "Elaboración de productos de panadería", "nombre_en": "Manufacture of bakery products",
                 "osm": ["shop=bakery"]},
        "4631": {"nombre_es": "Comercio al por mayor de alimentos", "osm": []},  # sin nombre_en
    }

    r = api.get("/actividades", headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    assert r.json() == [
        {"codigo": "1081", "nombre_es": "Elaboración de productos de panadería", "nombre_en": "Manufacture of bakery products"},
        {"codigo": "4631", "nombre_es": "Comercio al por mayor de alimentos", "nombre_en": None},  # la clave está, con null
    ]


def test_actividades_yaml_real_tiene_nombre_es_en_todas_las_entradas():
    entradas = yaml.safe_load((BACKEND / "config" / "actividades.yaml").read_text())
    assert entradas
    assert [k for k, e in entradas.items() if not e.get("nombre_es")] == []
    assert [k for k, e in entradas.items() if "descripcion" in e] == []  # nombre_es reemplaza a descripcion


# --- tablero --------------------------------------------------------------------------------------------------

def _sembrar(admin, tenant, filas):
    """filas: (lead, busqueda, fuente). Siembra con postgres; `tenants` limpia todo al terminar."""
    leads, busquedas = {f[0] for f in filas}, {f[1] for f in filas}
    with admin.begin() as c:
        for b in busquedas:
            c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:id, :t, 'CO', '{}')"),
                      {"id": b, "t": tenant})
        for lead in leads:
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) "
                           "VALUES (:id, :t, 'CO', 'sembrado', 'juridica')"), {"id": lead, "t": tenant})
        for lead, busqueda, fuente in filas:
            c.execute(text("INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                           "VALUES (:t, :l, :b, :f, 'https://ejemplo.invalid/x', 'lic')"),
                      {"t": tenant, "l": lead, "b": busqueda, "f": fuente})


OSM_ATRIBUCION = {"fuente": "osm_overpass", "texto": "© OpenStreetMap contributors",
                  "url": "https://www.openstreetmap.org/copyright"}
DATOS_ATRIBUCION = {"fuente": "datos_gov_co_rues", "texto": "Datos: Confecámaras vía datos.gov.co (CC BY-SA 4.0)",
                    "url": "https://creativecommons.org/licenses/by-sa/4.0/"}


@pytest.mark.parametrize("fuentes, esperado", [
    pytest.param(["osm_overpass"], [OSM_ATRIBUCION], id="solo_osm"),
    pytest.param(["osm_overpass", "datos_gov_co_rues"], [OSM_ATRIBUCION, DATOS_ATRIBUCION], id="osm_y_datos_gov"),
    pytest.param(["croma_supersociedades_co"], [], id="solo_croma"),
    pytest.param([], [], id="sin_leads"),
])
def test_tablero_atribucion_solo_de_fuentes_presentes(api, admin, usuarios, fuentes, esperado):
    _sembrar(admin, usuarios["tenant_a"], [(uuid4(), uuid4(), f) for f in fuentes])
    # Una fuente de B no cuenta para la atribución de A.
    _sembrar(admin, usuarios["tenant_b"], [(uuid4(), uuid4(), "datos_gov_co_rues")] if "datos_gov_co_rues" not in fuentes else [])

    r = api.get("/tablero/fuentes", headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    assert r.json()["atribuciones"] == esperado  # exacto y en orden


def test_tablero_devuelve_encontrados_y_unicos_del_tenant(api, admin, usuarios):
    l1, l2, l3, b1, b2 = (uuid4() for _ in range(5))
    _sembrar(admin, usuarios["tenant_a"], [
        (l1, b1, "osm_overpass"), (l1, b2, "osm_overpass"),  # el mismo lead en dos búsquedas: 2 encontrados, 1 único
        (l2, b1, "osm_overpass"), (l2, b1, "datos_gov_co_rues"),
    ])
    _sembrar(admin, usuarios["tenant_b"], [(l3, uuid4(), "osm_overpass")] * 1)

    como_a, como_b = _tablero(api, usuarios["a"]), _tablero(api, usuarios["b"])

    minimo = lambda f: {k: f[k] for k in ("fuente", "encontrados", "unicos")}  # noqa: E731
    assert [minimo(f) for f in como_a["fuentes"]] == [
        {"fuente": "datos_gov_co_rues", "encontrados": 1, "unicos": 1},
        {"fuente": "osm_overpass", "encontrados": 3, "unicos": 2},
    ]
    assert minimo(como_a["total"]) == {"fuente": "TOTAL", "encontrados": 4, "unicos": 2}  # l2 está en dos fuentes
    assert [minimo(f) for f in como_b["fuentes"]] == [{"fuente": "osm_overpass", "encontrados": 1, "unicos": 1}]
    assert minimo(como_b["total"]) == {"fuente": "TOTAL", "encontrados": 1, "unicos": 1}


def test_tablero_completa_con_null_lo_que_aun_no_se_calcula(api, admin, usuarios):
    _sembrar(admin, usuarios["tenant_a"], [(uuid4(), uuid4(), "osm_overpass")])

    t = _tablero(api, usuarios["a"])

    for clave in ("cobertura", "revisiones_pendientes"):
        assert t[clave] is None, clave  # null = "sin dato"; nunca [] ni 0
    # Sin filas en `costos`: costo, CPL y evals son "sin dato" (null), no "0".
    assert t["costo_evals"] is None
    for fila in [*t["fuentes"], t["total"]]:
        for clave in ("icp", "desperdicio_lista", "desperdicio_real", "costo_lista", "costo_real", "cpl_lista", "cpl_real",
                      "naturales_no_contactables"):
            assert fila[clave] is None, clave
        assert fila["cuenta_naturales"] is False


def _costo(admin, tenant, fuente, unidades, unitario, gratis=False):
    with admin.begin() as c:
        c.execute(text("INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, fuente, gratis) "
                       "VALUES (:t, 'overpass_query', :u, :c, 'USD', 'p', :f, :g)"),
                  {"t": tenant, "u": unidades, "c": unitario, "f": fuente, "g": gratis})


def test_tablero_devuelve_costo_y_cpl_como_decimales_en_string(api, admin, usuarios):
    a, osm = usuarios["tenant_a"], "osm_overpass"
    _sembrar(admin, a, [(uuid4(), uuid4(), osm), (uuid4(), uuid4(), osm)])
    _costo(admin, a, osm, 3, "0.10")
    _costo(admin, a, osm, 1, "0.10", gratis=True)
    _costo(admin, a, "evals", 1, "1.00")

    t = _tablero(api, usuarios["a"])

    (fila,) = t["fuentes"]
    assert (Decimal(fila["costo_lista"]), Decimal(fila["costo_real"])) == (Decimal("0.40"), Decimal("0.30"))
    assert (Decimal(fila["cpl_lista"]), Decimal(fila["cpl_real"])) == (Decimal("0.20"), Decimal("0.15"))
    assert all(isinstance(fila[k], str) for k in ("costo_lista", "costo_real", "cpl_lista", "cpl_real"))
    assert Decimal(t["total"]["cpl_lista"]) == Decimal("0.20") and Decimal(t["costo_evals"]) == Decimal("1.00")


def test_tablero_devuelve_null_para_cpl_sin_divisor(api, admin, usuarios):
    _costo(admin, usuarios["tenant_a"], "croma_supersociedades_co", 1, "0.50")  # costo y cero leads

    t = _tablero(api, usuarios["a"])

    (fila,) = t["fuentes"]
    assert Decimal(fila["costo_lista"]) == Decimal("0.50")
    for f in (fila, t["total"]):
        assert f["cpl_lista"] is None and f["cpl_real"] is None  # null, no "0" ni "0.0"


def test_tablero_no_mezcla_costos_de_otro_tenant(api, admin, usuarios):
    _sembrar(admin, usuarios["tenant_a"], [(uuid4(), uuid4(), "osm_overpass")])
    _costo(admin, usuarios["tenant_a"], "osm_overpass", 1, "0.10")
    _costo(admin, usuarios["tenant_b"], "osm_overpass", 1, "50")
    _costo(admin, usuarios["tenant_b"], "evals", 1, "50")

    t = _tablero(api, usuarios["a"])

    assert Decimal(t["total"]["costo_lista"]) == Decimal("0.10") and t["costo_evals"] is None


# --- de punta a punta -----------------------------------------------------------------------------------------

def test_flujo_completo_deja_leads_costos_y_cumplimiento_del_tenant(api, admin, usuarios):
    busqueda_id = _crear(api, usuarios["a"])

    r = _ejecutar(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["busqueda_id"] == busqueda_id
    assert cuerpo["estado"] == "completada"
    assert cuerpo["errores"] == [] and cuerpo["sin_fuente_para"] is None

    # Cuentas exactas, derivadas del fixture: OSM trae N elementos con nombre y datos.gov.co, sus filas jurídicas.
    esperados_osm = sum(1 for e in OSM["elements"] if e.get("tags", {}).get("name"))
    esperados_datos = sum(1 for f in FILAS if "NATURAL" not in f["organizacion_juridica"])
    assert cuerpo["encontrados"] == esperados_osm + esperados_datos
    assert cuerpo["nuevos"] == cuerpo["unicos"] == cuerpo["encontrados"]  # fixtures sin NIT repetido entre fuentes

    # Toda operación de salida escribió su costo, en el lote de la búsqueda y del tenant de A: una fila por request.
    with admin.connect() as c:
        costos = c.execute(text("SELECT tenant_id, lote_id, lead_id, proveedor FROM costos")).all()
    assert len(costos) == len(api.pedidas) == 2
    assert {c.proveedor for c in costos} == {"osm", "datos.gov.co"}
    assert {(c.tenant_id, str(c.lote_id), c.lead_id) for c in costos} == {(usuarios["tenant_a"], busqueda_id, None)}

    # Cada lead de A trae su cumplimiento completo, una sola vez; y nada quedó en B.
    leads_a = _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :a", a=usuarios["tenant_a"])
    assert leads_a == cuerpo["nuevos"]
    assert _contar(admin, "SELECT count(*) FROM leads l WHERE l.tenant_id = :a AND NOT EXISTS ("
                          "SELECT 1 FROM cumplimiento c WHERE c.lead_id = l.id)", a=usuarios["tenant_a"]) == 0
    assert _contar(admin, "SELECT count(*) FROM cumplimiento WHERE tenant_id = :a AND (fuente IS NULL OR licencia IS NULL "
                          "OR url_origen IS NULL OR as_of IS NULL)", a=usuarios["tenant_a"]) == 0
    # base_legal la setea AprobarMensaje en el 007 (0002 migración:68, 003 spec:344): hasta entonces es NULL en todos, y
    # sin ella el 007 no puede enviar. Si alguien la rellena acá (por ejemplo con 'persona_juridica...' a un lead de OSM,
    # que es 'desconocido' = natural), este assert lo delata.
    assert _contar(admin, "SELECT count(*) FROM cumplimiento WHERE tenant_id = :a AND base_legal IS NOT NULL",
                   a=usuarios["tenant_a"]) == 0
    assert _contar(admin, "SELECT count(DISTINCT lead_id) = count(*) FROM cumplimiento WHERE tenant_id = :a",
                   a=usuarios["tenant_a"]) is True
    assert _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :b", b=usuarios["tenant_b"]) == 0

    # ...y el tablero de A lo muestra, con la misma cuenta; el de B, vacío.
    tablero = _tablero(api, usuarios["a"])
    assert tablero["total"]["encontrados"] == cuerpo["encontrados"]
    assert tablero["total"]["unicos"] == cuerpo["unicos"]
    assert _tablero(api, usuarios["b"])["fuentes"] == []


def test_fuente_caida_no_tumba_la_busqueda_y_el_error_es_un_codigo(api, admin, usuarios):
    pedidas = []

    def responder(request):
        pedidas.append(request)
        if request.url.host == "www.datos.gov.co":
            return httpx.Response(500, json={"message": "Texto en español con datos del servidor"})
        return httpx.Response(200, json=OSM)

    api.app.state.transporte_http = httpx.MockTransport(responder)  # la fábrica lo lee en CADA request
    busqueda_id = _crear(api, usuarios["a"])

    r = _ejecutar(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "completada"  # OSM respondió
    assert cuerpo["errores"] == [{"fuente": "datos_gov_co_rues", "motivo": "no_disponible"}]  # código, no frase
    assert "servidor" not in r.text and "español" not in r.text
    assert cuerpo["encontrados"] > 0
    with admin.connect() as c:
        costos = c.execute(text("SELECT proveedor FROM costos WHERE tenant_id = :a"), {"a": usuarios["tenant_a"]}).all()
    assert len(costos) == len(pedidas)  # el intento fallido también gastó cómputo y quedó en el libro
    assert sorted({c.proveedor for c in costos}) == ["datos.gov.co", "osm"]
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "completada"


# --- composición: lo inyectable se lee por request y se re-fija en cada arranque -------------------------------

def test_la_fabrica_lee_el_transporte_en_cada_request_no_al_arrancar(api, usuarios):
    quien = {"n": 0}

    def contar_en(nombre):
        def responder(request):
            quien[nombre] = quien.get(nombre, 0) + 1
            return httpx.Response(200, json=OSM if request.url.host != "www.datos.gov.co" else FILAS,
                                  headers={"X-SODA2-Truth-Last-Modified": HEADER_AS_OF})
        return httpx.MockTransport(responder)

    api.app.state.transporte_http = contar_en("primero")
    assert _ejecutar(api, usuarios["a"], _crear(api, usuarios["a"])).status_code == 200
    api.app.state.transporte_http = contar_en("segundo")
    assert _ejecutar(api, usuarios["a"], _crear(api, usuarios["a"], ciiu="4752")).status_code == 200

    assert quien["primero"] >= 1 and quien["segundo"] >= 1  # el segundo request usó el transporte nuevo


def test_el_lifespan_re_fija_transporte_y_actividades_en_cada_arranque(entorno):
    import importlib

    app = importlib.import_module("app.main").app
    with TestClient(app):
        app.state.transporte_http = "pisado por un test"
        app.state.actividades_yaml = {"pisado": {}}
    with TestClient(app):  # un arranque nuevo no hereda lo que dejó el anterior
        assert isinstance(app.state.transporte_http, httpx.BaseTransport)
        assert not isinstance(app.state.transporte_http, httpx.MockTransport)
        real = yaml.safe_load((BACKEND / "config" / "actividades.yaml").read_text())
        assert app.state.actividades_yaml == real


# --- palabras clave y exclusiones: se guardan y se dice que no se aplican ---------------------------------------

def test_palabras_clave_y_exclusiones_se_guardan_y_figuran_como_ignoradas(api, admin, usuarios):
    r = _vista_previa(api, usuarios["a"], palabras_clave=["pan"], exclusiones=["industrial"])

    assert r.status_code == 201
    for fuente in r.json()["fuentes"]:
        assert {"palabras_clave", "exclusiones"} <= set(fuente["ignorados"]), fuente["fuente"]  # ninguna las aplica aún
    guardado = _contar(admin, "SELECT criterios FROM busquedas WHERE id = :id", id=r.json()["busqueda_id"])
    assert guardado["palabras_clave"] == ["pan"] and guardado["exclusiones"] == ["industrial"]


def test_sin_palabras_clave_ni_exclusiones_no_hay_nada_que_ignorar(api, usuarios):
    r = _vista_previa(api, usuarios["a"])
    assert r.status_code == 201
    for fuente in r.json()["fuentes"]:
        assert not {"palabras_clave", "exclusiones"} & set(fuente["ignorados"])


# --- geografía: país -> división (código nativo) -> ciudad (municipio) ---------------------------------------------

def test_geografia_sin_pais_lista_solo_los_paises_con_archivo(api_real, usuarios):
    api = api_real
    r = api.get("/geografia", headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    assert r.json() == {"paises": ["CO"]}  # MX, PE y BR no tienen archivo todavía: la UI no los ofrece


def test_geografia_de_colombia_trae_33_divisiones_con_codigo_comun_nativo_y_nombres(api_real, usuarios):
    api = api_real
    r = api.get("/geografia", params={"pais": "CO"}, headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    divisiones = r.json().get("divisiones", [])
    assert len(divisiones) == 33 and len({d["codigo_nativo"] for d in divisiones}) == 33  # 32 + Bogotá, D.C.
    assert len({d["iso_3166_2"] for d in divisiones}) == 33
    assert all(re.fullmatch(r"CO-[A-Z]{2,3}", d["iso_3166_2"]) and re.fullmatch(r"\d{2}", d["codigo_nativo"])
               and d["nombre_es"] and d["nombre_en"] and isinstance(d["municipios"], list) for d in divisiones)
    por_nativo = {d["codigo_nativo"]: d for d in divisiones}
    assert (por_nativo["73"]["iso_3166_2"], por_nativo["73"]["nombre_es"]) == ("CO-TOL", "Tolima")
    assert (por_nativo["11"]["iso_3166_2"], por_nativo["11"]["nombre_es"]) == ("CO-DC", "Bogotá, D.C.")
    assert [d["codigo_nativo"] for d in divisiones] == sorted(por_nativo)  # estable: por código nativo


def test_geografia_de_un_pais_sin_archivo_es_404(api_real, usuarios):
    api = api_real
    assert api.get("/geografia", params={"pais": "PE"}, headers=_bearer(usuarios["a"])).status_code == 404


@pytest.mark.parametrize("cambios, esperado", [
    pytest.param({"departamento": "Tolima", "ciudad": None}, [("departamento", "desconocido")], id="nombre_en_vez_de_codigo"),
    pytest.param({"departamento": "00", "ciudad": None}, [("departamento", "desconocido")], id="codigo_que_no_existe"),
    pytest.param({"departamento": "73", "ciudad": "Bogotá"}, [("ciudad", "desconocido")], id="ciudad_de_otra_division"),
    pytest.param({"departamento": None, "ciudad": "Ibagué"}, [("departamento", "requerido")], id="ciudad_sin_division"),
    pytest.param({"pais": "PE", "departamento": None, "ciudad": None}, [("pais", "desconocido")], id="pais_sin_archivo_de_geografia"),
])
def test_geografia_invalida_da_422_con_codigo(api, admin, usuarios, cambios, esperado):
    api.app.state.geografia = GEOGRAFIA_DE_PRUEBA

    r = _vista_previa(api, usuarios["a"], **cambios)

    assert r.status_code == 422
    assert [(e["campo"], e["codigo"]) for e in r.json()["errores"]] == esperado
    assert _contar(admin, "SELECT count(*) FROM busquedas WHERE tenant_id = :a", a=usuarios["tenant_a"]) == 0


def _cuerpo(request):
    return request.content.decode() + str(request.url)


def test_tolima_e_ibague_llegan_a_datos_gov_con_sus_camaras_y_a_osm_con_la_ciudad(api, tmp_path, usuarios):
    # Cámara SINTÉTICA "99" que cubre el departamento 73: el dato real de Tolima no está en camaras_co.yaml (no se inventa).
    camaras = tmp_path / "camaras.yaml"
    camaras.write_text('"99": {nombre: "Ficticia", municipio_sede: "Ibagué", departamentos: ["73"]}\n')
    api.app.state.camaras_yaml = camaras
    api.app.state.geografia = GEOGRAFIA_DE_PRUEBA

    busqueda_id = _crear(api, usuarios["a"], departamento="73", ciudad="Ibagué")
    r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200 and r.json()["estado"] == "completada" and r.json()["errores"] == []
    datos = [q for q in api.pedidas if q.url.host == "www.datos.gov.co"]
    osm = [q for q in api.pedidas if q.url.host != "www.datos.gov.co"]
    assert len(datos) == 1 and len(osm) == 1
    from urllib.parse import unquote_plus
    assert "codigo_camara in('99')" in unquote_plus(_cuerpo(datos[0])).replace('"', "'")
    assert "Ibagu" in unquote_plus(_cuerpo(osm[0]))


VICHADA = {"iso_3166_2": "CO-VID", "codigo_nativo": "99", "nombre_es": "Vichada", "nombre_en": "Vichada",
           "municipios": [{"codigo_nativo": "99001", "nombre": "Puerto Carreño"}]}


def test_un_departamento_sin_camaras_en_el_yaml_real_no_tumba_la_busqueda(api, admin, usuarios):
    # Con las 58 cámaras (T054) Tolima ya tiene cámaras; Vichada (99) sigue sin ninguna con sede allí.
    api.app.state.geografia = {"CO": {"pais": "CO", "divisiones": [VICHADA]}}
    busqueda_id = _crear(api, usuarios["a"], departamento="99", ciudad="Puerto Carreño")

    r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200  # no un 500 por CriterioNoSoportado
    cuerpo = r.json()
    assert cuerpo["estado"] == "completada"  # OSM sí corrió, con la ciudad
    assert cuerpo["errores"] == [{"fuente": "datos_gov_co_rues", "motivo": "criterio_no_soportado"}]
    assert not [q for q in api.pedidas if q.url.host == "www.datos.gov.co"]  # falló antes de cualquier request
    # En el libro del lote: ni una fila de datos.gov.co (no hubo request) y exactamente una de OSM.
    with admin.connect() as c:
        filas = c.execute(text("SELECT proveedor FROM costos WHERE lote_id = :l"), {"l": busqueda_id}).all()
    assert [f.proveedor for f in filas] == ["osm"]


# --- 015: resultado por fuente -------------------------------------------------------------------------------

def _osm_con(api, respuesta):
    """Overpass responde `respuesta` (una Response o una excepción a lanzar); datos.gov.co sigue con las filas de prueba."""
    previo = api.app.state.transporte_http

    def responder(request):
        if request.url.host == "www.datos.gov.co":
            return previo.handle_request(request)
        api.pedidas.append(request)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    api.app.state.transporte_http = httpx.MockTransport(responder)


@pytest.mark.parametrize("causa", [
    pytest.param(httpx.ReadTimeout("t"), id="overpass_timeout"),
    pytest.param(httpx.ConnectError("c"), id="overpass_sin_conexion"),
])
def test_departamento_sin_camaras_y_overpass_caido_no_da_500(api, admin, usuarios, causa):
    """Un departamento sin cámaras en el YAML real (datos.gov.co: criterio no soportado) y Overpass caído por red:
    antes, la excepción de httpx no la atrapa nadie y la API devuelve 500 con la búsqueda en `error`.
    Era Tolima; con las 58 cámaras (T054) Tolima tiene cámaras y el caso pasa a Vichada."""
    api.app.state.geografia = {"CO": {"pais": "CO", "divisiones": [VICHADA]}}
    _osm_con(api, causa)
    busqueda_id = _crear(api, usuarios["a"], departamento="99", ciudad="Puerto Carreño")

    r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200
    assert r.json()["por_fuente"] == {
        "osm_overpass": {"estado": "no_disponible", "encontrados": 0},
        "datos_gov_co_rues": {"estado": "no_soporta_criterio", "encontrados": 0}}
    assert r.json()["estado"] == "error"  # las dos fallaron; la respuesta sigue siendo 200
    assert _contar(admin, "SELECT estado FROM busquedas WHERE id = :id", id=busqueda_id) == "error"



def test_ejecutar_devuelve_por_fuente(api, usuarios):
    busqueda_id = _crear(api, usuarios["a"])

    r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200
    por_fuente = r.json()["por_fuente"]
    assert set(por_fuente) == {"osm_overpass", "datos_gov_co_rues"}
    assert all(set(v) == {"estado", "encontrados"} and v["estado"] == "con_resultados" and v["encontrados"] > 0
               for v in por_fuente.values())
    assert sum(v["encontrados"] for v in por_fuente.values()) == r.json()["encontrados"]
    assert CODIGO.match(por_fuente["osm_overpass"]["estado"])  # un código, no una frase


def test_overpass_sin_elementos_es_sin_resultados_y_la_busqueda_completa(api, usuarios):
    _osm_con(api, httpx.Response(200, json={"osm3s": {"timestamp_osm_base": "2026-10-01T00:00:00Z"}, "elements": []}))
    busqueda_id = _crear(api, usuarios["a"])

    r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200 and r.json()["estado"] == "completada"
    assert r.json()["por_fuente"]["osm_overpass"] == {"estado": "sin_resultados", "encontrados": 0}
    assert r.json()["por_fuente"]["datos_gov_co_rues"]["estado"] == "con_resultados"


def test_log_de_fuente_caida_no_trae_el_mensaje(api, usuarios, caplog):
    import logging

    _osm_con(api, httpx.ReadTimeout("ACME SAS 900123456 https://overpass.test/?data=secreto"))
    busqueda_id = _crear(api, usuarios["a"])

    with caplog.at_level(logging.DEBUG):
        r = _ejecutar_o_500(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200
    registros = [x for x in caplog.records if "osm_overpass" in x.getMessage()]
    assert registros and "ReadTimeout" in registros[0].getMessage()
    for x in caplog.records:
        assert x.exc_info is None and x.exc_text is None
        assert "ACME" not in x.getMessage() and "secreto" not in x.getMessage() and "900123456" not in x.getMessage()


def test_actividades_devuelve_el_catalogo_real_ampliado(api, usuarios):
    r = api.get("/actividades", headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    por_codigo = {a["codigo"]: a for a in r.json()}
    assert len(por_codigo) >= 20
    for codigo in ("4711", "5611", "4752", "4773", "4771", "9602", "4520", "6201", "4923"):
        assert codigo in por_codigo, codigo
    assert por_codigo["6201"]["nombre_es"] and por_codigo["6201"]["nombre_en"]


def test_tablero_devuelve_el_embudo_por_fuente_y_total_solo_con_conteos(api, admin, usuarios):
    tenant, lead, busqueda = usuarios["tenant_a"], uuid4(), uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES (:b, :t, 'CO', '{}')"),
                  {"b": busqueda, "t": tenant})
        c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular, enriquecido_en, contactable, "
                       "telefono_cifrado, telefono_canal) VALUES (:l, :t, 'CO', 'Z', 'juridica', now(), true, :x, 'sitio_web')"),
                  {"l": lead, "t": tenant, "x": b"x" * 40})
        c.execute(text("INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                       "VALUES (:t, :l, :b, 'osm_overpass', 'u', 'l')"), {"t": tenant, "l": lead, "b": busqueda})
        c.execute(text("INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
                       "VALUES (:t, :l, true, now(), 1)"), {"t": tenant, "l": lead})
    _costo(admin, tenant, None, 1, "0.07")

    t = _tablero(api, usuarios["a"])

    campos = ("enriquecidos", "contactables", "con_telefono", "calificados")
    osm = next(f for f in t["fuentes"] if f["fuente"] == "osm_overpass")
    assert [osm[k] for k in campos] == [1, 1, 1, 1] and [t["total"][k] for k in campos] == [1, 1, 1, 1]
    sin = next(f for f in t["fuentes"] if f["fuente"] == "sin_atribuir")
    assert [sin[k] for k in campos] == [None] * 4  # costo sin lead: no aplica, no un 0 inventado
    assert all(isinstance(osm[k], int) for k in campos)
