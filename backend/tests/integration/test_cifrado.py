import ast
import logging
import re
import traceback
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from app.cli import Persistencia, main
from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import Actividad, EmpresaCruda
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from app.seguridad.catalogo_sensibles import CIFRADAS, CONDICIONALES
from tests.falsos import FuenteFalsa, RegistroCostosFalso
from tests.integration.ayudas_osm import FIXTURE, buscar_osm

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
REPOSITORIO = APP / "modulos" / "descubrimiento" / "infraestructura" / "persistencia" / "repositorio_leads.py"
# PostgresCalificaciones (008) lee leads para el chequeo juridica+cumplimiento antes de importar: solo
# tipo_titular e id, nunca nombre/direccion/nombre_cifrado/direccion_cifrada.
CALIFICACIONES = APP / "modulos" / "calificacion" / "infraestructura" / "persistencia" / "postgres_calificaciones.py"
# modelos.py y el catálogo nombran columnas, no ejecutan SQL sobre ellas.
PERMITIDOS = (REPOSITORIO, CALIFICACIONES, APP / "modelos.py", APP / "seguridad" / "catalogo_sensibles.py")
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


class _FuenteConNombre(FuenteFalsa):
    """Para correr la CLI: una fuente que devuelve un desconocido con nombre y dirección."""

    def __init__(self, *, meta, registro_costos, lote_id, **kwargs):
        super().__init__(meta, registro_costos, lote_id, (_empresa("desconocido"),))


def _sensibles_de_la_fixture():
    tags = [e["tags"] for e in FIXTURE["elements"]]
    return [t["name"] for t in tags if "name" in t] + [t["addr:street"] for t in tags if "addr:street" in t] \
        + [t["addr:housenumber"] for t in tags if "addr:housenumber" in t]


def test_contacto_no_aparece_en_logs(rt, tenants, cifrador, caplog, capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app_rt@localhost/sin_uso")  # la CLI lee repo_url de Settings
    caplog.set_level(logging.DEBUG)  # raíz: incluye httpx, sqlalchemy y psycopg
    sensibles = [*_sensibles_de_la_fixture(), NOMBRE, DIRECCION]
    assert len(sensibles) > 4  # la fixture sí trae nombres y direcciones que buscar

    buscar_osm(rt, tenants["a"], cifrador)
    persistencia = Persistencia(RepositorioLeadsPostgres(rt, tenants["a"], cifrador), RegistroCostosFalso())
    assert main(["buscar", "--tenant", str(tenants["a"]), "--pais", "CO", "--ciiu", "4711", "--ciudad", "Bogotá"],
                catalogo={"osm_overpass": _FuenteConNombre}, persistencia=persistencia) == 0

    captura = capsys.readouterr()
    volcado = caplog.text + captura.out + captura.err
    assert volcado  # el resumen de la CLI sí imprime algo
    assert [s for s in sensibles if s in volcado] == []


def _identidad_en_claro(self, e, lead_id):
    return {"nombre": e.nombre, "direccion": e.direccion, "nombre_cifrado": None, "direccion_cifrada": None}


@pytest.mark.parametrize("motor", ["rt", "admin"])
def test_una_violacion_de_check_no_filtra_nombre_ni_direccion(motor, request, tenants, cifrador, monkeypatch, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    # Un bug que guarde en claro a un desconocido: el CHECK lo frena. Con app_rt (RLS) Postgres no manda la fila
    # en el DETAIL; con un rol que la saltea (admin) sí la manda: ese caso mata a ErrorPersistencia(str(e.orig)).
    engine = request.getfixturevalue(motor)
    monkeypatch.setattr(RepositorioLeadsPostgres, "_identidad", _identidad_en_claro)

    with pytest.raises(Exception) as exc:
        _crear(engine, tenants["a"], cifrador, "desconocido")

    captura = capsys.readouterr()
    volcado = "".join(traceback.format_exception(exc.value)) + caplog.text + captura.out + captura.err
    assert type(exc.value) is ErrorPersistencia
    assert exc.value.__cause__ is None and exc.value.__suppress_context__  # from None
    assert NOMBRE not in volcado and DIRECCION not in volcado


def test_contacto_no_queda_en_claro_en_columnas_no_catalogadas(rt, admin, tenants, cifrador):
    buscar_osm(rt, tenants["a"], cifrador)

    with admin.connect() as c:
        filas = c.execute(text("SELECT nombre, direccion, web, ciudad FROM leads WHERE tenant_id = :t"),
                          {"t": tenants["a"]}).all()
    assert len(filas) == len([e for e in FIXTURE["elements"] if e["tags"].get("name")])
    assert {(nombre, direccion) for nombre, direccion, *_ in filas} == {(None, None)}
    assert [f for f in filas if any(n in str(f) for n in _sensibles_de_la_fixture())] == []
