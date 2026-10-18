import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from app.modulos.descubrimiento.dominio.modelos import Actividad, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from app.seguridad.catalogo_sensibles import CIFRADAS, CONDICIONALES

APP = Path(__file__).resolve().parents[2] / "app"
REPOSITORIO = APP / "modulos" / "descubrimiento" / "infraestructura" / "persistencia" / "repositorio_leads.py"
# modelos.py y el catálogo nombran columnas, no ejecutan SQL sobre ellas.
PERMITIDOS = (REPOSITORIO, APP / "modelos.py", APP / "seguridad" / "catalogo_sensibles.py")
NOMBRE = "Tienda Doña Rosa"  # sintéticos
DIRECCION = "Calle 10 # 5-20"


def _empresa(tipo):
    return EmpresaCruda(
        pais="CO", nombre=NOMBRE, fuente="osm_overpass", url_origen="https://www.openstreetmap.org/node/1",
        as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("4711", "CIIU"), ciudad="Bogotá",
        direccion=DIRECCION, tipo_titular=tipo, id_fiscal="900123456" if tipo == "juridica" else None)


def _crear(rt, tenant, cifrador, tipo):
    repo = RepositorioLeadsPostgres(rt, tenant, cifrador)
    lead_id, _ = repo.obtener_o_crear_lead(_empresa(tipo), "ODbL")
    return repo, lead_id


def _crudo(admin, lead_id):
    with admin.connect() as c:
        return c.execute(text("SELECT nombre, direccion, nombre_cifrado, direccion_cifrada FROM leads WHERE id = :id"),
                         {"id": lead_id}).one()


@pytest.mark.parametrize("tipo", ["desconocido", "natural"])
def test_nombre_y_direccion_de_no_juridica_van_cifrados(rt, admin, tenants, cifrador, tipo):
    repo, lead_id = _crear(rt, tenants["a"], cifrador, tipo)

    nombre, direccion, nombre_cifrado, direccion_cifrada = _crudo(admin, lead_id)

    assert nombre is None and direccion is None
    assert nombre_cifrado is not None and NOMBRE.encode() not in bytes(nombre_cifrado)
    assert direccion_cifrada is not None and DIRECCION.encode() not in bytes(direccion_cifrada)
    assert cifrador.descifrar("nombre_cifrado", bytes(nombre_cifrado), tenants["a"], lead_id) == NOMBRE
    assert cifrador.descifrar("direccion_cifrada", bytes(direccion_cifrada), tenants["a"], lead_id) == DIRECCION
    lead = repo.obtener_lead(lead_id)
    assert (lead.nombre, lead.direccion) == (NOMBRE, DIRECCION)


def test_nombre_y_direccion_de_juridica_van_en_claro(rt, admin, tenants, cifrador):
    repo, lead_id = _crear(rt, tenants["a"], cifrador, "juridica")

    assert _crudo(admin, lead_id) == (NOMBRE, DIRECCION, None, None)
    lead = repo.obtener_lead(lead_id)
    assert (lead.nombre, lead.direccion) == (NOMBRE, DIRECCION)


def test_obtener_lead_de_otro_tenant_no_devuelve_nada(rt, tenants, cifrador):
    _, lead_id = _crear(rt, tenants["a"], cifrador, "desconocido")

    assert RepositorioLeadsPostgres(rt, tenants["b"], cifrador).obtener_lead(lead_id) is None


def test_el_catalogo_apunta_a_columnas_que_existen(admin):
    with admin.connect() as c:
        existentes = {tuple(f) for f in c.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'")).all()}
    assert (CIFRADAS | CONDICIONALES) <= existentes


def test_nombre_y_direccion_en_claro_solo_para_juridicas(rt, admin, tenants, cifrador):
    for tipo in ("juridica", "desconocido", "natural"):
        _crear(rt, tenants["a"], cifrador, tipo)

    with admin.connect() as c:
        for tabla, columna in sorted(CONDICIONALES):
            filas = c.execute(text(f"SELECT tipo_titular, {columna} FROM {tabla} WHERE tenant_id = :t"),
                              {"t": tenants["a"]}).all()
            assert {tipo for tipo, _ in filas} == {"juridica", "desconocido", "natural"}
            assert {tipo: valor for tipo, valor in filas if tipo != "juridica"} == {"desconocido": None, "natural": None}


SQL_SOBRE_IDENTIDAD = re.compile(
    r"(?is)(leads\s*\.\s*(nombre|direccion)\w*|\b(nombre_cifrado|direccion_cifrada)\b"
    r"|select\b[^;\"']*\b(nombre|direccion)\b[^;\"']*\bfrom\s+(public\.)?leads\b)")


def test_nombre_solo_se_lee_por_el_repositorio():
    sueltos = [str(f.relative_to(APP)) for f in APP.rglob("*.py")
               if f not in PERMITIDOS and SQL_SOBRE_IDENTIDAD.search(f.read_text())]
    assert sueltos == []
