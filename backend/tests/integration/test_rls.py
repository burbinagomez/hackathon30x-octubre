import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app import db

# fuente_cache queda fuera: es global, sin tenant_id. Guarda datos públicos de gobierno, no del tenant,
# y no se expone por API (spec, Decisiones técnicas).
EXCLUIDAS = {"fuente_cache", "usuarios"}
# usuarios queda fuera: app_rt no tiene privilegios sobre ella (entra solo por tenant_de_usuario), así que el test de
# tablas daría permission denied y no probaría RLS. Su aislamiento lo prueban test_usuarios_tiene_rls y test_usuarios_repo.
TABLAS = ["tenants", "busquedas", "leads", "lead_fuentes", "cumplimiento", "costos", "contactos", "calificaciones"]
# calificaciones no tiene id: su fila se identifica por lead_id.
COLUMNA_ID = {"calificaciones": "lead_id"}
# app_rt solo tiene SELECT (tenants) o SELECT e INSERT (calificaciones): UPDATE y DELETE fallan por privilegio.
SIN_UPDATE_NI_DELETE = {"tenants", "calificaciones"}
SIN_DELETE = {"contactos"}  # app_rt no borra contactos: el historial de envíos no se pierde
PRIVILEGIO_INSUFICIENTE = "42501"  # también es el sqlstate de una violación de política RLS
FK_VIOLADA = "23503"


def _url(nombre):
    url = os.environ.get(nombre)
    if not url:
        pytest.fail(f"falta {nombre}: los tests de integración fallan, no se saltan (R6)")
    return url


@pytest.fixture
def rt():
    engine = db.crear_engine(_url("TEST_DATABASE_URL"))
    yield engine
    engine.dispose()


@pytest.fixture
def datos():
    """Tenant A con una fila en cada tabla, y tenant B con una búsqueda y dos leads propios. Sembrado como postgres.

    Los dos leads de B son el control positivo de `test_tenant_b_no_fusiona_con_lead_de_a`: sin una fila de B a la
    que apuntar, el rojo de la FK se confundiría con un UPDATE sin efecto.
    """
    a, b = uuid4(), uuid4()
    ids = {"tenants": a, "busquedas": uuid4(), "leads": uuid4(), "lead_fuentes": uuid4(),
           "cumplimiento": uuid4(), "costos": uuid4(), "contactos": uuid4(), "lead_sin_cumplimiento": uuid4(),
           "busqueda_b": uuid4(), "lead_b": uuid4(), "lead_b2": uuid4(), "a": a, "b": b,
           # Una fila de `costos` por camino de las vistas de costo (ver el INSERT de abajo).
           "costo_lote": uuid4(), "costo_canal": uuid4(), "costo_evals": uuid4(), "lote_evals": uuid4()}
    admin = create_engine(_url("TEST_ADMIN_DATABASE_URL"))
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO tenants (id, nombre) VALUES (:a, 'A'), (:b, 'B')"), ids)
            c.execute(text("INSERT INTO busquedas (id, tenant_id, pais, criterios) VALUES "
                           "(:busquedas, :a, 'CO', '{}'), (:busqueda_b, :b, 'CO', '{}')"), ids)
            c.execute(text("INSERT INTO leads (id, tenant_id, pais, nombre, tipo_titular) VALUES "
                           "(:leads, :a, 'CO', 'A1', 'juridica'), (:lead_sin_cumplimiento, :a, 'CO', 'A2', 'juridica'), "
                           "(:lead_b, :b, 'CO', 'B1', 'juridica'), (:lead_b2, :b, 'CO', 'B2', 'juridica')"), ids)
            c.execute(text("INSERT INTO lead_fuentes (id, tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                           "VALUES (:lead_fuentes, :a, :leads, :busquedas, 'osm_overpass', 'u', 'l')"), ids)
            # opt_out_at: control positivo de v_leads_con_opt_out.
            c.execute(text("INSERT INTO cumplimiento (id, tenant_id, lead_id, fuente, licencia, url_origen, as_of, opt_out_at) "
                           "VALUES (:cumplimiento, :a, :leads, 'f', 'l', 'u', now(), now())"), ids)
            c.execute(text("INSERT INTO contactos (id, tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo) "
                           "VALUES (:contactos, :a, :leads, :busquedas, 'email', 'a', 'c')"), ids)
            # El libro de A, una fila por camino de las vistas de costo: la de lote (`lead_id` nulo) sobre la fuente de
            # la `lead_fuentes` de A —es la que se prorratea sobre su lead y la que le da una `parte` a
            # `v_costo_por_lead`—, una con canal, una de `evals` (aparte del libro) y la de siempre, sin fuente ni lote,
            # que cubre `sin_atribuir` y el desperdicio. `lote_evals` no es la búsqueda: el lote de evals es la corrida.
            c.execute(text("INSERT INTO costos (id, tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, "
                           "fuente, canal, lead_id, lote_id, gratis) VALUES "
                           "(:costos, :a, 'croma_consulta', 1, 0, 'USD', 'croma', NULL, NULL, NULL, NULL, true), "
                           "(:costo_lote, :a, 'overpass_query', 3, 0.10, 'USD', 'osm', 'osm_overpass', NULL, NULL, :busquedas, false), "
                           "(:costo_canal, :a, 'email_envio', 1, 0.05, 'USD', 'osm', 'osm_overpass', 'email', :leads, NULL, false), "
                           "(:costo_evals, :a, 'llm_tokens_in', 1, 1.00, 'USD', 'anthropic', 'evals', NULL, NULL, :lote_evals, false)"), ids)
            c.execute(text("INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
                           "VALUES (:a, :leads, true, now(), 1)"), ids)
        ids["calificaciones"] = ids["leads"]
        yield ids
    finally:
        with admin.begin() as c:
            # El control positivo de la FK de `fusionado_en` deja un lead de B apuntando a otro: se suelta antes de
            # borrar, para que el orden de las filas no tenga que decidir si la FK se satisface.
            c.execute(text("UPDATE leads SET fusionado_en = NULL WHERE tenant_id IN (:a, :b)"), ids)
            for t in ["contactos", "calificaciones", "lead_fuentes", "cumplimiento", "costos", "leads", "busquedas"]:
                c.execute(text(f"DELETE FROM {t} WHERE tenant_id IN (:a, :b)"), ids)
            c.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"), ids)
        admin.dispose()


# INSERT de una fila nueva con el tenant_id de A. Usa el lead sin cumplimiento y otra fuente, para que
# ningún UNIQUE la rechace antes que la política.
INSERT_CON_TENANT_DE_A = {
    "tenants": "INSERT INTO tenants (nombre) VALUES ('intruso')",
    "busquedas": "INSERT INTO busquedas (tenant_id, pais, criterios) VALUES (:a, 'CO', '{}')",
    "leads": "INSERT INTO leads (tenant_id, pais, nombre, tipo_titular) VALUES (:a, 'CO', 'intruso', 'juridica')",
    "lead_fuentes": "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                    "VALUES (:a, :lead_sin_cumplimiento, :busquedas, 'otra', 'u', 'l')",
    "cumplimiento": "INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
                    "VALUES (:a, :lead_sin_cumplimiento, 'f', 'l', 'u', now())",
    "costos": "INSERT INTO costos (tenant_id, tipo, unidades, costo_unitario, moneda, proveedor, gratis) "
              "VALUES (:a, 'croma_consulta', 1, 0, 'USD', 'croma', true)",
    "contactos": "INSERT INTO contactos (tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo) "
                 "VALUES (:a, :lead_sin_cumplimiento, :busquedas, 'email', 'a', 'c')",
    "calificaciones": "INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
                      "VALUES (:a, :lead_sin_cumplimiento, true, now(), 1)",
}


def _como_b(rt, datos, sql):
    with db.unidad_de_trabajo(rt, datos["b"]) as c:
        return c.execute(text(sql), datos)


def _rechazado(rt, datos, sql, sqlstate):
    with pytest.raises(DBAPIError) as exc:
        _como_b(rt, datos, sql)
    assert exc.value.orig.sqlstate == sqlstate


def test_la_lista_cubre_todas_las_tablas_de_public(rt):
    with rt.connect() as c:
        en_public = set(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars())
    assert en_public == set(TABLAS) | EXCLUIDAS


@pytest.mark.parametrize("tabla", TABLAS)
def test_tenant_b_no_accede_a_datos_de_a(rt, datos, tabla):
    col = COLUMNA_ID.get(tabla, "id")
    fila_de_a = f"WHERE {col} = '{datos[tabla]}'"
    assert _como_b(rt, datos, f"SELECT * FROM {tabla} {fila_de_a}").all() == []

    if tabla in SIN_UPDATE_NI_DELETE:
        # La siembra corre con postgres.
        for sql in (f"UPDATE {tabla} SET {col} = {col} {fila_de_a}", f"DELETE FROM {tabla} {fila_de_a}"):
            _rechazado(rt, datos, sql, PRIVILEGIO_INSUFICIENTE)
    else:
        assert _como_b(rt, datos, f"UPDATE {tabla} SET id = id {fila_de_a}").rowcount == 0
        if tabla in SIN_DELETE:
            _rechazado(rt, datos, f"DELETE FROM {tabla} {fila_de_a}", PRIVILEGIO_INSUFICIENTE)
        else:
            assert _como_b(rt, datos, f"DELETE FROM {tabla} {fila_de_a}").rowcount == 0

    _rechazado(rt, datos, INSERT_CON_TENANT_DE_A[tabla], PRIVILEGIO_INSUFICIENTE)


def test_tenant_b_no_muda_una_fila_propia_a_a(rt, datos):
    # WITH CHECK: B no puede dejar su búsqueda con el tenant_id de A. Sin WHERE a propósito: si el UPDATE
    # lee columnas, Postgres también aplica el USING a la fila nueva y el test no probaría el WITH CHECK.
    # RLS lo acota a las filas de B, y B tiene una sola búsqueda.
    _rechazado(rt, datos, "UPDATE busquedas SET tenant_id = :a", PRIVILEGIO_INSUFICIENTE)


# Con su propio tenant_id y un id de A (lead o búsqueda): la política lo deja pasar y una FK simple no pasa por RLS.
COLGAR_DE_LEAD_DE_A = {
    "lead_fuentes": "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                    "VALUES (:b, :lead_sin_cumplimiento, :busqueda_b, 'f', 'u', 'l')",
    "cumplimiento": "INSERT INTO cumplimiento (tenant_id, lead_id, fuente, licencia, url_origen, as_of) "
                    "VALUES (:b, :lead_sin_cumplimiento, 'f', 'l', 'u', now())",
    "lead_fuentes_busqueda": "INSERT INTO lead_fuentes (tenant_id, lead_id, busqueda_id, fuente, url_origen, licencia) "
                             "VALUES (:b, :lead_b, :busquedas, 'f', 'u', 'l')",
    "contactos": "INSERT INTO contactos (tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo) "
                 "VALUES (:b, :lead_sin_cumplimiento, :busqueda_b, 'email', 'a', 'c')",
    "contactos_busqueda": "INSERT INTO contactos (tenant_id, lead_id, busqueda_id, canal, asunto, cuerpo) "
                          "VALUES (:b, :lead_b, :busquedas, 'email', 'a', 'c')",
    "calificaciones": "INSERT INTO calificaciones (tenant_id, lead_id, calificado, calificado_en, minutos) "
                      "VALUES (:b, :lead_sin_cumplimiento, true, now(), 1)",
}


@pytest.mark.parametrize("tabla", sorted(COLGAR_DE_LEAD_DE_A))
def test_tenant_b_no_cuelga_filas_de_un_lead_de_a(rt, datos, tabla):
    _rechazado(rt, datos, COLGAR_DE_LEAD_DE_A[tabla], FK_VIOLADA)


def test_tenant_b_no_fusiona_con_lead_de_a(rt, datos):
    """La FK de `fusionado_en` tiene que ser compuesta, `(tenant_id, fusionado_en) → leads (tenant_id, id)`.

    Una FK simple no pasa por RLS —el chequeo de integridad corre como el dueño de la tabla— y la fila del lead de A
    existe, así que hoy el UPDATE de B entra. Con la compuesta, el par (tenant de B, lead de A) no existe.
    """
    # Control positivo: el mismo UPDATE hacia otro lead de B sí funciona (si no, el rojo de abajo sería un UPDATE
    # sin efecto por privilegio o por política, no la FK).
    assert _como_b(rt, datos, "UPDATE leads SET fusionado_en = :lead_b2 WHERE id = :lead_b").rowcount == 1
    _rechazado(rt, datos, "UPDATE leads SET fusionado_en = :leads WHERE id = :lead_b", FK_VIOLADA)


# Vistas: las 6 de los slices anteriores y las 6 del libro de costos (0010). Con datos solo de A: la siembra trae
# costos (uno de lote sobre `osm_overpass`, uno con canal, uno de evals y uno sin fuente), un lead con su
# `lead_fuentes` de osm_overpass y su calificación, un opt-out y un contacto.
VISTAS = ["v_tablero_fuentes", "v_atribuciones", "v_leads_icp", "v_cpql", "v_leads_con_opt_out", "v_tasa_respuesta_canal",
          "v_costos", "v_costo_evals", "v_prorrateo", "v_desperdicio", "v_costo_por_lead", "v_costo_por_canal"]


def _filas_de_la_vista(rt, tenant, vista):
    with db.unidad_de_trabajo(rt, tenant) as c:
        return c.execute(text(f"SELECT * FROM {vista}")).all()


@pytest.mark.parametrize("vista", VISTAS)
def test_tenant_b_no_accede_a_datos_de_a_en_vistas(rt, datos, vista):
    """(El nombre del card es `::test_tenant_b_no_accede_a_datos_de_a[vista]`; `[tabla]` ya es de la tabla.)

    La mutación que pone este test en rojo es sacarle `security_invoker` a la vista **que lee la tabla base**
    (`v_costos`, `v_costo_evals`, `v_leads_icp`, `v_tablero_fuentes`, `v_atribuciones`, `v_cpql`,
    `v_leads_con_opt_out`, `v_tasa_respuesta_canal`): una vista anidada solo sobre otras vistas conserva su
    protección, porque las vistas de abajo siguen corriendo como `app_rt`. `v_prorrateo` es el caso extremo —sus
    dos entradas son vistas— y para que B vea una fila suya hay que sacarle la opción a `v_costos` **y** a
    `v_leads_icp` (comprobado en la base aparte `sab_t009`).
    """
    # Control positivo: sin él, el 0 de B no probaría nada.
    assert len(_filas_de_la_vista(rt, datos["a"], vista)) >= 1
    # También la fila TOTAL de `v_tablero_fuentes`: con `security_invoker` y sin datos de B, `HAVING count(*) > 0`
    # es lo único que la deja fuera, y un `count(*)` de 0 la agregaría con ceros.
    assert _filas_de_la_vista(rt, datos["b"], vista) == []


def test_la_lista_cubre_todas_las_vistas_de_public(rt):
    with rt.connect() as c:
        en_public = set(c.execute(text("SELECT viewname FROM pg_views WHERE schemaname = 'public'")).scalars())
    assert en_public == set(VISTAS)


def test_toda_vista_es_security_invoker(rt):
    with rt.connect() as c:
        vistas = dict(c.execute(text(
            "SELECT c.relname, coalesce(c.reloptions, '{}') FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'v'")).all())
    assert set(VISTAS) <= set(vistas)  # una lista vacía dejaría el test verde sin probar nada
    sin_la_opcion = sorted(v for v, opciones in vistas.items() if "security_invoker=true" not in opciones)
    assert sin_la_opcion == []


def test_usuarios_tiene_rls(rt):
    with rt.connect() as c:
        activa = c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.usuarios'::regclass")).scalar_one()
        politicas = {tabla: c.execute(text("SELECT qual, with_check FROM pg_policies "
                                           "WHERE schemaname = 'public' AND tablename = :t"), {"t": tabla}).all()
                     for tabla in ("usuarios", "leads")}
    assert activa is True
    assert len(politicas["leads"]) == 1  # la referencia: sin ella, igualar dos listas vacías pasaría
    # Igualdad con la política de leads, no subcadenas: "tenant_id = app.tenant_id OR true" las cumpliría.
    assert politicas["usuarios"] == politicas["leads"]
