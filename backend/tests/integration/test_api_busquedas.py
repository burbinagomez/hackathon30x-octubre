"""T031 [MIN]: Nueva búsqueda y Tablero por la API, contra Postgres con RLS y las fuentes reales con transporte falso.

Contrato que fija este archivo para el verde (T032):
- la raíz de composición lee `app.state.transporte_http` (un `httpx.BaseTransport`) y `app.state.actividades_yaml`
  (el contenido de config/actividades.yaml); el lifespan los deja con los valores de producción y los tests los pisan;
- vista previa: 201; ejecutar: 200; sin la búsqueda (o ajena): 404; ya no es borrador: 409; cuerpo inválido: 422;
- los errores y los motivos son códigos, nunca una frase.
Sin red: los dos hosts (Overpass y datos.gov.co) los atiende un MockTransport. Datos sintéticos.
"""
import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import yaml
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
    return api


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
    # [MIN]: sin `contar` no hay conteo ni costos, y la API no inventa números: null, nunca 0.
    assert cuerpo["fuentes"][0] == {"fuente": "datos_gov_co_rues", "conteo": None, "motivo": "sin_conteo",
                                    "ignorados": ["ciudad"], "truncado": False}
    for clave in ("costo_vista_previa_usd", "costo_estimado_usd", "costo_maximo_usd", "creditos_restantes_mes",
                  "requests_restantes_24h", "dentro_del_tope"):
        assert cuerpo[clave] is None, clave  # el tope no se aplica todavía: no se declara "dentro" ni "fuera"
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


# --- de punta a punta -----------------------------------------------------------------------------------------

def test_flujo_completo_deja_leads_costos_y_cumplimiento_del_tenant(api, admin, usuarios):
    busqueda_id = _crear(api, usuarios["a"])

    r = _ejecutar(api, usuarios["a"], busqueda_id)

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["busqueda_id"] == busqueda_id
    assert cuerpo["estado"] == "completada"
    assert cuerpo["errores"] == [] and cuerpo["sin_fuente_para"] is None
    assert cuerpo["nuevos"] > 0 and cuerpo["encontrados"] >= cuerpo["unicos"] >= cuerpo["nuevos"]

    # Toda operación de salida escribió su costo, en el lote de la búsqueda y del tenant de A.
    costos = admin.connect().execute(text(
        "SELECT tenant_id, lote_id, lead_id, proveedor FROM costos")).all()
    assert {c.proveedor for c in costos} == {"osm", "datos.gov.co"}
    assert {(c.tenant_id, str(c.lote_id), c.lead_id) for c in costos} == {(usuarios["tenant_a"], busqueda_id, None)}
    # Cada lead de A trae su fila de cumplimiento, y nada quedó en B.
    leads_a = _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :a", a=usuarios["tenant_a"])
    assert leads_a == cuerpo["nuevos"]
    assert _contar(admin, "SELECT count(*) FROM cumplimiento WHERE tenant_id = :a", a=usuarios["tenant_a"]) == leads_a
    assert _contar(admin, "SELECT count(*) FROM leads WHERE tenant_id = :b", b=usuarios["tenant_b"]) == 0

    # ...y el tablero de A lo muestra, con la misma cuenta; el de B, vacío.
    tablero = _tablero(api, usuarios["a"])
    assert tablero["total"]["encontrados"] == cuerpo["encontrados"]
    assert tablero["total"]["unicos"] == cuerpo["unicos"]
    assert _tablero(api, usuarios["b"])["fuentes"] == []
