"""T015 [MIN] (security): import del CSV de Dapta y CPQL por la API, contra Postgres con RLS. Datos sintéticos, sin red.

Contrato:
- `POST /calificaciones/importar`: cuerpo `text/csv` ≤ 1 MB -> 200 con el resumen; otro tipo -> 415; más grande -> 413;
  ilegible -> 422; tarifa `null` -> 409; `dapta_csv` deshabilitado en fuentes.yaml -> 503. Motivos y errores son códigos.
- `GET /calificaciones/cpql`: filas de `v_cpql`, montos como string, null = "sin dato".
- Los dos con sesión: sin token -> 401 (**Mutación `endpoint_sin_sesion`**: el router fuera del include con `Depends`).
"""
import re
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

CODIGO = re.compile(r"^[a-z][a-z0-9_]*$")
CSV = "text/csv"


def _lead(admin, tenant_id):
    lead_id = uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) VALUES "
                       "(:id, :t, 'CO', 'Empresa', 'juridica')"), {"id": lead_id, "t": tenant_id})
        c.execute(text("INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
                       "VALUES (:t, :id, 'osm_overpass', 'ODbL', 'u', now())"), {"id": lead_id, "t": tenant_id})
    return lead_id


def _importar(api, quien, cuerpo: bytes, tipo=CSV):
    return api.post("/calificaciones/importar", content=cuerpo, headers={**_bearer(quien), "Content-Type": tipo})


def _csv(*filas: str) -> bytes:
    return ("lead_id,calificado,fecha,minutos\n" + "".join(f + "\n" for f in filas)).encode()


@pytest.mark.parametrize("metodo, ruta", [("post", "/calificaciones/importar"), ("get", "/calificaciones/cpql")])
def test_sin_sesion_es_401(cliente, metodo, ruta):
    assert getattr(cliente, metodo)(ruta).status_code == 401


def test_importar_y_ver_el_cpql_con_montos_en_string(cliente, admin, usuarios):
    lead_id = _lead(admin, usuarios["tenant_a"])

    r = _importar(cliente, usuarios["a"], _csv(f"{lead_id},si,2026-10-01T12:00:00+00:00,2.1", "x,talvez,ayer,1"))

    assert r.status_code == 200
    resumen = r.json()
    assert (resumen["importadas"], resumen["duplicadas"], resumen["conflictos"]) == (1, 0, 0)
    assert len(resumen["rechazadas"]) == 1 and resumen["rechazadas"][0]["fila"] == 2
    assert CODIGO.match(resumen["rechazadas"][0]["motivo"])

    cpql = cliente.get("/calificaciones/cpql", headers=_bearer(usuarios["a"]))
    assert cpql.status_code == 200
    filas = {f["fuente"]: f for f in cpql.json()["fuentes"]}
    # 2.1 min -> 3 minutos facturables x 0.333 = 0.999, sin fuente: va a sin_atribuir y no tiene CPQL propio.
    assert Decimal(filas["sin_atribuir"]["costo_lista"]) == Decimal("0.999")
    assert isinstance(filas["sin_atribuir"]["costo_lista"], str)
    assert filas["sin_atribuir"]["cpql_lista"] is None
    total = cpql.json()["total"]
    assert total["calificados"] == 1 and Decimal(total["cpql_lista"]) == Decimal("0.999")


def test_otro_tenant_no_ve_el_cpql_ni_importa_leads_ajenos(cliente, admin, usuarios):
    lead_de_a = _lead(admin, usuarios["tenant_a"])

    r = _importar(cliente, usuarios["b"], _csv(f"{lead_de_a},si,2026-10-01T12:00:00+00:00,2"))

    assert r.status_code == 200 and r.json()["ref_desconocida"] == 1
    assert cliente.get("/calificaciones/cpql", headers=_bearer(usuarios["b"])).json() == {"fuentes": [], "total": None}


def test_cuerpo_que_no_es_csv_es_415(cliente, usuarios):
    r = _importar(cliente, usuarios["a"], b"{}", tipo="application/json")

    assert r.status_code == 415 and r.json() == {"codigo": "tipo_no_soportado"}


def test_cuerpo_de_mas_de_1_mb_es_413(cliente, usuarios):
    r = _importar(cliente, usuarios["a"], b"a" * (1024 * 1024 + 1))

    assert r.status_code == 413 and r.json() == {"codigo": "archivo_muy_grande"}


@pytest.mark.parametrize("cuerpo", [b"\xff\xfe no es utf-8", _csv(*[f"{uuid4()},si,2026-10-01,1"] * 1001)])
def test_archivo_ilegible_o_sobre_el_limite_de_filas_es_422(cliente, usuarios, cuerpo):
    r = _importar(cliente, usuarios["a"], cuerpo)

    assert r.status_code == 422 and r.json() == {"codigo": "archivo_invalido"}


def test_tarifa_pendiente_es_409_y_no_escribe_nada(cliente, admin, usuarios):
    lead_id = _lead(admin, usuarios["tenant_a"])
    cliente.app.state.tarifas = {**cliente.app.state.tarifas, "dapta": None}

    r = _importar(cliente, usuarios["a"], _csv(f"{lead_id},si,2026-10-01T12:00:00+00:00,2"))

    assert r.status_code == 409 and r.json() == {"codigo": "tarifa_pendiente"}
    with admin.connect() as c:
        assert c.execute(text("SELECT count(*) FROM calificaciones WHERE lead_id = :l"), {"l": lead_id}).scalar() == 0


def test_calificador_deshabilitado_es_503(cliente, usuarios):
    cliente.app.state.calificador = None  # `calificadores.dapta_csv.habilitado: false` en fuentes.yaml

    r = _importar(cliente, usuarios["a"], _csv())

    assert r.status_code == 503 and r.json() == {"codigo": "calificador_deshabilitado"}
