"""La 0007 es el DDL que Daniel aprobó (2026-10-18) en el plan de la 006: el archivo no difiere ni en un comentario."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
ARCHIVO = RAIZ / "supabase" / "migrations" / "0007_enriquecimiento.sql"


def _bloque_aprobado() -> str:
    plan = (RAIZ / "specs" / "006-enriquecedor-contactable" / "plan.md").read_text(encoding="utf-8")
    seccion = plan[plan.index("## Migración 0007 — APROBADA"):]
    return re.search(r"```sql\n(.*?)```", seccion, re.S).group(1)


def test_la_0007_es_el_ddl_aprobado_de_plan_md():
    bloque = _bloque_aprobado()
    assert "CHECK (email_canal IN ('sitio_web','osm_contacto'))" in bloque  # el aprobado, no la propuesta
    assert ARCHIVO.exists()
    assert ARCHIVO.read_text(encoding="utf-8") == bloque


def test_cada_vista_repite_security_invoker_y_no_toca_costos():
    sql = _bloque_aprobado()
    vistas = re.findall(r"CREATE (?:OR REPLACE )?VIEW (\S+) WITH \(security_invoker = true\)", sql)
    assert sorted(vistas) == ["public.v_leads_icp", "public.v_tablero_fuentes"]
    assert len(re.findall(r"CREATE (?:OR REPLACE )?VIEW", sql)) == 2
    assert "costos" not in sql


def test_v_tablero_fuentes_conserva_las_columnas_de_la_0006_al_principio():
    sql = _bloque_aprobado()
    vista = sql[sql.index("VIEW public.v_tablero_fuentes"):sql.index("UNION ALL")]
    alias = re.findall(r"AS (\w+),?$", vista, re.M)
    assert alias == ["encontrados", "unicos", "icp", "con_telefono", "contactables", "no_contactables_politica"]
    assert vista.index("SELECT lf.fuente,") < vista.index("AS encontrados")
