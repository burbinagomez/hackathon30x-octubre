"""Exportar elegibles para Dapta (spec 008, paso 1, versión de la noche): un CSV listo para la hoja de Google de la
plantilla "Call a list of contacts from google sheets" (columnas to_number, first_name, lead_id) más ciudad, fuentes y
licencia. Solo jurídicas con teléfono publicado y sin baja; el teléfono se descifra solo acá. Sin red."""
import csv
import io
from uuid import uuid4

from sqlalchemy import text

from tests.integration.test_auth import _bearer, cliente, entorno, usuarios, verificador  # noqa: F401

RUTA = "/calificaciones/exportar"


def _lead(cliente, admin, tenant_id, *, nombre="Supermercado Uno SAS", titular="juridica", telefono="+573001112233",
          baja=False, fuente="osm_overpass", licencia="ODbL"):
    lead_id = uuid4()
    cifrador = cliente.app.state.cifrador
    cifrado = None if telefono is None else cifrador.cifrar("telefono_cifrado", telefono, tenant_id, lead_id)
    nombre_cifrado = None if titular == "juridica" else cifrador.cifrar("nombre_cifrado", nombre, tenant_id, lead_id)
    with admin.begin() as c:
        c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, nombre_cifrado, tipo_titular, ciudad, telefono_cifrado, "
                       "telefono_canal) VALUES (:id, :t, 'CO', :n, :nc, :tt, 'Bogotá', :tel, :canal)"),
                  {"id": lead_id, "t": tenant_id, "n": nombre if titular == "juridica" else None, "nc": nombre_cifrado, "tt": titular,
                   "tel": cifrado, "canal": None if telefono is None else "osm_contacto"})
        c.execute(text("INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of, opt_out_at) "
                       "VALUES (:t, :id, :f, :l, 'u', now(), :baja)"),
                  {"id": lead_id, "t": tenant_id, "f": fuente, "l": licencia, "baja": "2026-10-01" if baja else None})
        b = c.execute(text("INSERT INTO busquedas (tenant_id, pais, criterios) VALUES (:t, 'CO', '{}'::jsonb) RETURNING id"),
                      {"t": tenant_id}).scalar_one()
        c.execute(text("INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                       "VALUES (:t, :id, :b, :f, 'u', :l)"), {"t": tenant_id, "id": lead_id, "b": b, "f": fuente, "l": licencia})
    return lead_id


def _filas(r):
    return list(csv.DictReader(io.StringIO(r.text)))


def test_sin_sesion_es_401(cliente):
    assert cliente.get(RUTA).status_code == 401


def test_exporta_solo_juridicas_con_telefono_y_sin_baja(cliente, admin, usuarios):
    t = usuarios["tenant_a"]
    bueno = _lead(cliente, admin, t)
    _lead(cliente, admin, t, titular="natural")          # persona natural: nunca
    _lead(cliente, admin, t, telefono=None)              # sin teléfono: no calificable
    _lead(cliente, admin, t, baja=True)                  # se dio de baja

    r = cliente.get(RUTA, headers=_bearer(usuarios["a"]))

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    filas = _filas(r)
    assert [f["lead_id"] for f in filas] == [str(bueno)]
    assert filas[0]["to_number"] == "+573001112233"
    assert filas[0]["first_name"] == "Supermercado Uno SAS"
    assert (filas[0]["fuentes"], filas[0]["licencia"]) == ("osm_overpass", "ODbL")


def test_no_exporta_leads_de_otro_tenant(cliente, admin, usuarios):
    _lead(cliente, admin, usuarios["tenant_b"])
    assert _filas(cliente.get(RUTA, headers=_bearer(usuarios["a"]))) == []


def test_celdas_que_empiezan_con_formula_van_neutralizadas(cliente, admin, usuarios):
    _lead(cliente, admin, usuarios["tenant_a"], nombre="=HYPERLINK(\"http://x\")")
    fila = _filas(cliente.get(RUTA, headers=_bearer(usuarios["a"])))[0]
    assert fila["first_name"].startswith("'=")
