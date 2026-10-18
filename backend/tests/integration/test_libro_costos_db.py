"""El resto del DDL de la 005 (spec:422-430) que no entró en la 0006 congelada ni en la 0010.

Nombra cada objeto a propósito: sin esto la suite seguiría verde aunque la migración no existiera, porque
`test_migraciones` compara `modelos.py` contra la base (si los dos lados faltan, no hay drift) y las vistas
de `test_vistas_costos` no leen estas columnas. `fijar_estimados` (T025/T026) las escribe; acá solo se fija
que estén, con su tipo y su nulabilidad.
"""
from sqlalchemy import text

# `ejecutada_en` es cuándo corrió la búsqueda; los dos costos los escribe la vista previa (spec:359-364).
# Nullable: el borrador nace sin ellos y las filas que ya existían tampoco los tienen.
COLUMNAS = {
    "costo_estimado_usd": "numeric",
    "costo_maximo_usd": "numeric",
    "ejecutada_en": "timestamp with time zone",
}

INDICES = {
    "costos_tenant_lote_idx": ("costos", "tenant_id, lote_id"),
    "lead_fuentes_busqueda_fuente_idx": ("lead_fuentes", "busqueda_id, fuente"),
}


def test_busquedas_tiene_las_columnas_del_estimado(admin):
    with admin.connect() as c:
        filas = dict(c.execute(text(
            "SELECT column_name, (data_type, is_nullable) FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'busquedas' AND column_name = ANY(:n)"),
            {"n": list(COLUMNAS)}).all())
    assert filas == {nombre: (tipo, "YES") for nombre, tipo in COLUMNAS.items()}


def test_los_dos_indices_existen_con_sus_columnas(admin):
    with admin.connect() as c:
        definiciones = dict(c.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(:n)"),
            {"n": list(INDICES)}).all())
    assert sorted(definiciones) == sorted(INDICES)
    for nombre, (tabla, columnas) in INDICES.items():
        assert f"ON public.{tabla} USING btree ({columnas})" in definiciones[nombre], definiciones[nombre]
