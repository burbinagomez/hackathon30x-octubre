import ast
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from app.modulos.descubrimiento.dominio.modelos import Actividad, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from app.seguridad.catalogo_sensibles import CIFRADAS, CONDICIONALES

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
REPOSITORIO = APP / "modulos" / "descubrimiento" / "infraestructura" / "persistencia" / "repositorio_leads.py"
# modelos.py y el catálogo nombran columnas, no ejecutan SQL sobre ellas.
PERMITIDOS = (REPOSITORIO, APP / "modelos.py", APP / "seguridad" / "catalogo_sensibles.py")
NOMBRE = "Tienda Doña Rosa"  # sintéticos
DIRECCION = "Calle 10 # 5-20"
CLARO = {"nombre_cifrado": NOMBRE, "direccion_cifrada": DIRECCION}  # lo que guarda cada columna cifrada


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

    assert _crudo(admin, lead_id)[:2] == (None, None)
    # Recorre el catálogo: una columna cifrada nueva sin su texto en CLARO hace fallar el primer assert.
    assert CIFRADAS and {columna for _, columna in CIFRADAS} == set(CLARO)
    with admin.connect() as c:
        for tabla, columna in sorted(CIFRADAS):
            tipo_de_dato = c.execute(text("SELECT data_type FROM information_schema.columns "
                                          "WHERE table_name = :t AND column_name = :c"), {"t": tabla, "c": columna}).scalar()
            guardado = c.execute(text(f"SELECT {columna} FROM {tabla} WHERE id = :id"), {"id": lead_id}).scalar()
            assert tipo_de_dato == "bytea"
            assert guardado is not None and CLARO[columna].encode() not in bytes(guardado)
            assert cifrador.descifrar(columna, bytes(guardado), tenants["a"], lead_id) == CLARO[columna]
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
    assert CIFRADAS and CONDICIONALES
    with admin.connect() as c:
        existentes = {tuple(f) for f in c.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'")).all()}
    assert (CIFRADAS | CONDICIONALES) <= existentes


def test_nombre_y_direccion_en_claro_solo_para_juridicas(rt, admin, tenants, cifrador):
    assert CONDICIONALES
    for tipo in ("juridica", "desconocido", "natural"):
        _crear(rt, tenants["a"], cifrador, tipo)

    with admin.connect() as c:
        for tabla, columna in sorted(CONDICIONALES):
            filas = c.execute(text(f"SELECT tipo_titular, {columna} FROM {tabla} WHERE tenant_id = :t"),
                              {"t": tenants["a"]}).all()
            assert {tipo for tipo, _ in filas} == {"juridica", "desconocido", "natural"}
            assert {tipo: valor for tipo, valor in filas if tipo != "juridica"} == {"desconocido": None, "natural": None}


SQL_SOBRE_LEADS = re.compile(r"(?is)\b(from|join|update|into)\s+(public\.)?leads\b|^\s*(public\.)?leads\s*$")


def _texto(nodo):
    """El texto que un nodo arma con literales: 'a' 'b', 'a' + 'b' y f'...{x}...'. None si no es solo literales."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        izq, der = _texto(nodo.left), _texto(nodo.right)
        return None if izq is None or der is None else izq + der
    if isinstance(nodo, ast.JoinedStr):
        return "".join(_texto(v) or "\0" for v in nodo.values)
    return None


def menciona_la_tabla_leads(codigo: str) -> bool:
    """SQL o API de SQLAlchemy sobre la tabla leads, venga como venga armada."""
    for nodo in ast.walk(ast.parse(codigo)):
        texto = _texto(nodo)
        if texto is not None and SQL_SOBRE_LEADS.search(texto):
            return True
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "app.modelos" and any(a.name in ("leads", "*") for a in nodo.names):
            return True
        if isinstance(nodo, ast.Attribute) and nodo.attr == "leads":  # modelos.leads, app.modelos.leads
            return True
    return False


@pytest.mark.parametrize("codigo", [
    'C = "SELECT nombre FROM " "leads"',
    'C = "SELECT nombre " + "FROM leads"',
    'C = text("SELECT * FROM leads")',
    'C = f"UPDATE leads SET nombre = {x}"',
    'C = "INSERT INTO public.leads (nombre) VALUES (1)"',
    'C = "SELECT 1 FROM lead_fuentes JOIN leads ON true"',
    'from app.modelos import leads\nC = select(leads)',
    'from app.modelos import leads\nC = leads.c.nombre',
    'from app.modelos import leads\nC = leads.columns["nombre"]',
    'from app import modelos\nC = modelos.leads',
    'C = metadata.tables["leads"]',
])
def test_el_escaneo_ve_las_formas_de_llegar_a_leads(codigo):
    assert menciona_la_tabla_leads(codigo)


@pytest.mark.parametrize("codigo", [
    'C = "SELECT id FROM lead_fuentes"', 'C = "los leads de hoy"', 'from app.modelos import costos\nC = costos.c.tipo',
])
def test_el_escaneo_no_se_alarma_con_lo_inocente(codigo):
    assert not menciona_la_tabla_leads(codigo)


def test_nombre_solo_se_lee_por_el_repositorio():
    sueltos = [str(f.relative_to(BACKEND)) for carpeta in ("app", "evals", "scripts") for f in (BACKEND / carpeta).rglob("*.py")
               if f not in PERMITIDOS and menciona_la_tabla_leads(f.read_text())]
    assert sueltos == []
