"""La 0006 (antes 0004) es el DDL que el dueño aprobó (2026-10-18, con security OK): el archivo no difiere ni en un comentario."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def test_la_0006_es_el_ddl_v2_aprobado_de_plan_md():
    plan = (RAIZ / "specs" / "005-libro-costos-busqueda" / "plan.md").read_text(encoding="utf-8")
    seccion = plan[plan.index("### DDL de la 0004 v2"):]
    bloque = re.search(r"```sql\n(.*?)```", seccion, re.S).group(1)
    assert "tenant_de_usuario(p_auth_user_id uuid)" in bloque  # el v2, no el v1 superseded
    assert (RAIZ / "supabase" / "migrations" / "0006_libro_costos_busqueda.sql").read_text(encoding="utf-8") == bloque
