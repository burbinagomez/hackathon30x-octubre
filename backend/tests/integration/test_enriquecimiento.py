"""EnriquecerLead contra Postgres real: repo, costos y cifrado de verdad; Croma, sitio web y jev falsos. Sin red."""
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.dominio.errores import ErrorPersistencia
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda, ResultadoEnriquecimiento
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
from app.modulos.enriquecimiento.aplicacion.enriquecer_lead import EnriquecerLead
from app.modulos.enriquecimiento.dominio.puertos import ContactoPublicado, VerificacionTitular
from app.modulos.enriquecimiento.infraestructura.adaptadores.jev_clasificador import JevClasificador
from tests.falsos import EnriquecedorFalso, JevFalso, VerificadorFalso

TELEFONO = "+57 602 555 0101"  # sintético
EMAIL = "ventas@andinos.invalid"
MATCH = VerificacionTitular("juridica", "match_unico")
SITIO = {"andinos.invalid": ContactoPublicado((EMAIL,), ((TELEFONO, "sitio_web"),), "ok")}


def _empresa(nombre: str, web: str | None = None, tipo: str = "desconocido") -> EmpresaCruda:
    return EmpresaCruda(pais="CO", nombre=nombre, fuente="osm_co", url_origen="https://ejemplo.invalid/osm",
                        as_of=datetime(2026, 10, 1, tzinfo=UTC), actividad=Actividad("5229", "CIIU"),
                        tipo_titular=tipo, ciudad="Cali", direccion="Calle 1 # 2-3", web=web)


@pytest.fixture
def mundo(rt, tenants, cifrador):
    """Repo y costos reales del tenant A, con una búsqueda creada por el repo."""
    repo = RepositorioLeadsPostgres(rt, tenants["a"], cifrador)
    busqueda = repo.crear_busqueda(CriteriosICP("CO", {}))
    return repo, PostgresCostos(rt, tenants["a"]), busqueda


def _sembrar(repo, busqueda: UUID, empresa: EmpresaCruda) -> UUID:
    lead_id, _ = repo.obtener_o_crear_lead(empresa, "odbl")
    repo.agregar_lead_fuente(lead_id, busqueda, empresa, "odbl")
    return lead_id


def _caso(repo, costos, por_lead=None, sitio=None, salida=None, cortar_en=None, falla_en=frozenset(), jev=True):
    verificador = VerificadorFalso(costos, por_lead, cortar_en)
    clasificador = JevFalso(salida, costos, falla_en=falla_en) if jev else None
    return EnriquecerLead(repo, verificador, EnriquecedorFalso(costos, sitio), clasificador), verificador


def _con_icp(admin, busqueda):
    with admin.begin() as c:
        c.execute(text("UPDATE busquedas SET descripcion_icp = 'agentes de carga' WHERE id = :id"), {"id": busqueda})


def _fila(admin, lead_id, columnas: str):
    with admin.connect() as c:
        return c.execute(text(f"SELECT {columnas} FROM leads WHERE id = :id"), {"id": lead_id}).one_or_none()


def _costos(admin, tenant) -> list[tuple]:
    with admin.connect() as c:
        return [tuple(f) for f in c.execute(text(
            "SELECT tipo, lead_id, lote_id FROM costos WHERE tenant_id = :t ORDER BY tipo"), {"t": tenant})]


def _solicitudes(admin, lead_id) -> list[dict]:
    with admin.connect() as c:
        return c.execute(text("SELECT solicitudes FROM cumplimiento WHERE lead_id = :id"), {"id": lead_id}).scalar()


def test_desconocido_con_match_unico_pasa_a_juridica_en_claro(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos"))
    with admin.begin() as c:  # una entrada previa no se pisa: el UPDATE agrega, no reemplaza
        c.execute(text("""UPDATE cumplimiento SET solicitudes = '[{"tipo": "baja"}]' WHERE lead_id = :id"""), {"id": lead})
    caso, _ = _caso(repo, costos, por_lead={lead: MATCH})

    caso.ejecutar(busqueda)

    assert _fila(admin, lead, "tipo_titular, nombre, nombre_cifrado, direccion, direccion_cifrada") == (
        "juridica", "Transportes Andinos", None, "Calle 1 # 2-3", None)
    solicitudes = _solicitudes(admin, lead)
    assert len(solicitudes) == 2 and solicitudes[0] == {"tipo": "baja"}
    nueva = solicitudes[1]
    assert set(nueva) == {"tipo", "motivo", "fuente", "ts"}  # ni nombre ni dirección en la entrada
    assert (nueva["tipo"], nueva["motivo"], nueva["fuente"]) == ("paso_a_claro", "match_unico", "croma_rues_co")


def test_juridica_con_match_unico_no_agrega_entrada(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", tipo="juridica"))
    caso, _ = _caso(repo, costos, por_lead={lead: MATCH})

    caso.ejecutar(busqueda)

    assert _fila(admin, lead, "enriquecido_en").enriquecido_en is not None  # se procesó
    assert _solicitudes(admin, lead) == []  # ya estaba en claro: no hubo paso_a_claro


def test_otro_tenant_no_escribe_el_lead_ajeno(rt, admin, tenants, mundo, cifrador):
    repo, _, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos"))
    ajeno = RepositorioLeadsPostgres(rt, tenants["b"], cifrador)
    antes = _fila(admin, lead, "*")

    try:
        ajeno.guardar_enriquecimiento(lead, ResultadoEnriquecimiento(
            "juridica", (TELEFONO, "sitio_web"), (EMAIL, "sitio_web"), True, None))
    except ErrorPersistencia:
        pass  # lanzar con rowcount 0 vale; escribir no

    assert _fila(admin, lead, "*") == antes
    assert _solicitudes(admin, lead) == []


def test_email_y_telefono_se_guardan_cifrados(admin, tenants, mundo, cifrador):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", web="andinos.invalid"))
    caso, _ = _caso(repo, costos, por_lead={lead: MATCH}, sitio=SITIO)

    caso.ejecutar(busqueda)

    f = _fila(admin, lead, "telefono_cifrado, email_cifrado, telefono_canal, email_canal")
    assert f is not None and f.telefono_cifrado is not None and f.email_cifrado is not None
    assert TELEFONO.encode() not in bytes(f.telefono_cifrado) and EMAIL.encode() not in bytes(f.email_cifrado)
    assert cifrador.descifrar("telefono_cifrado", bytes(f.telefono_cifrado), tenants["a"], lead) == TELEFONO
    assert cifrador.descifrar("email_cifrado", bytes(f.email_cifrado), tenants["a"], lead) == EMAIL
    assert (f.telefono_canal, f.email_canal) == ("sitio_web", "sitio_web")


def test_sin_enriquecer_no_devuelve_otro_tenant_ni_ya_enriquecidos(rt, admin, tenants, mundo, cifrador):
    repo, _, busqueda = mundo
    hecho = _sembrar(repo, busqueda, _empresa("Ya Enriquecido"))
    pendiente = _sembrar(repo, busqueda, _empresa("Pendiente Ltda"))
    _sembrar(repo, repo.crear_busqueda(CriteriosICP("CO", {})), _empresa("Otra Búsqueda SAS"))  # mismo tenant
    with admin.begin() as c:
        c.execute(text("UPDATE leads SET enriquecido_en = now(), razon_no_contactable = 'persona_natural' WHERE id = :id"),
                  {"id": hecho})

    leads = repo.sin_enriquecer(busqueda)

    assert [(x.id, x.nombre) for x in leads] == [(pendiente, "Pendiente Ltda")]  # nombre descifrado por el repo
    assert RepositorioLeadsPostgres(rt, tenants["b"], cifrador).sin_enriquecer(busqueda) == []


def test_limite_agotado_corta_y_deja_lo_guardado(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    leads = [_sembrar(repo, busqueda, _empresa(f"Empresa {i}")) for i in range(3)]
    caso, verificador = _caso(repo, costos, cortar_en=2)

    resumen = caso.ejecutar(busqueda)

    assert resumen.cortado is True and verificador.llamadas == 2  # no siguió después del corte
    assert resumen.procesados == 1
    enriquecidos = [x for x in leads if _fila(admin, x, "enriquecido_en").enriquecido_en is not None]
    assert len(enriquecidos) == 1  # el anterior quedó; el cortado y el siguiente, sin tocar
    assert _costos(admin, tenants["a"]) == [("croma_consulta", enriquecidos[0], None)]  # la fila es del que quedó


def test_no_encaja_no_borra_el_lead(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    with admin.begin() as c:
        c.execute(text("UPDATE busquedas SET descripcion_icp = 'agentes de carga' WHERE id = :id"), {"id": busqueda})
    lead = _sembrar(repo, busqueda, _empresa("Panadería La Espiga", tipo="juridica"))
    caso, _ = _caso(repo, costos, salida={"etiqueta": "no_encaja", "probabilidad": 0.1})

    caso.ejecutar(busqueda)

    assert _fila(admin, lead, "encaje").encaje == "no_encaja"


def test_osm_desconocido_con_rues_y_sitio_queda_contactable(admin, tenants, mundo):
    # La jerarquía osm_contacto sobre sitio_web la cubre el unit de canal; acá, el camino completo.
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", web="andinos.invalid"))
    caso, _ = _caso(repo, costos, por_lead={lead: MATCH}, sitio=SITIO)

    resumen = caso.ejecutar(busqueda)

    assert _fila(admin, lead, "contactable, razon_no_contactable").contactable is True
    assert _fila(admin, lead, "razon_no_contactable").razon_no_contactable is None
    assert (resumen.procesados, resumen.contactables) == (1, 1)


def test_lead_sin_dominio_no_genera_web_fetch(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Sin Web SAS"))
    caso, _ = _caso(repo, costos, por_lead={lead: MATCH})

    caso.ejecutar(busqueda)

    assert [t for t, _, _ in _costos(admin, tenants["a"])] == ["croma_consulta"]
    assert _fila(admin, lead, "razon_no_contactable").razon_no_contactable == "sin_canal_publicado"


def test_persona_natural_de_osm_sigue_no_contactable(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Don Pedro Pérez"))
    caso, _ = _caso(repo, costos, por_lead={lead: VerificacionTitular("desconocido", "ambiguo")})

    caso.ejecutar(busqueda)

    f = _fila(admin, lead, "tipo_titular, contactable, razon_no_contactable, enriquecido_en, nombre")
    assert f is not None  # no se borra
    assert (f.tipo_titular, f.contactable, f.razon_no_contactable, f.nombre) == (
        "desconocido", False, "persona_natural", None)
    assert f.enriquecido_en is not None


def test_costos_van_al_lead_nunca_al_lote(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    with admin.begin() as c:
        c.execute(text("UPDATE busquedas SET descripcion_icp = 'agentes de carga' WHERE id = :id"), {"id": busqueda})
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", web="andinos.invalid"))
    caso, _ = _caso(repo, costos, por_lead={lead: MATCH}, sitio=SITIO)

    caso.ejecutar(busqueda)

    assert _costos(admin, tenants["a"]) == [("croma_consulta", lead, None), ("jev_tokens", lead, None),
                                            ("web_fetch", lead, None)]


def test_lead_ya_enriquecido_no_se_reprocesa(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    _sembrar(repo, busqueda, _empresa("Transportes Andinos", web="andinos.invalid"))
    caso, _ = _caso(repo, costos, sitio=SITIO)
    caso.ejecutar(busqueda)
    antes = len(_costos(admin, tenants["a"]))

    resumen = caso.ejecutar(busqueda)

    assert antes > 0
    assert len(_costos(admin, tenants["a"])) == antes and resumen.procesados == 0


def test_jev_caido_en_un_lead_lo_deja_sin_clasificar_y_sigue(admin, tenants, mundo, caplog):
    caplog.set_level(logging.DEBUG)  # ningún nivel lleva datos del lead, no solo WARNING
    repo, costos, busqueda = mundo
    _con_icp(admin, busqueda)
    leads = [_sembrar(repo, busqueda, _empresa(f"Empresa {i}", tipo="juridica")) for i in range(3)]
    caido = leads[1]
    caso, _ = _caso(repo, costos, falla_en={caido})

    resumen = caso.ejecutar(busqueda)

    assert (resumen.procesados, resumen.clasificados, resumen.sin_clasificar, resumen.cortado) == (3, 2, 1, False)
    filas = {x: _fila(admin, x, "enriquecido_en, encaje") for x in leads}
    assert all(f.enriquecido_en is not None for f in filas.values())  # marcado: no se reintenta solo
    assert filas[caido].encaje is None and {filas[x].encaje for x in leads if x != caido} == {"encaja"}
    assert ("jev_tokens", caido, None) in _costos(admin, tenants["a"])  # la fila en 0 es del lead caído
    assert "JevNoDisponible" in caplog.text
    assert "Empresa" not in caplog.text and "Cali" not in caplog.text  # solo la clase, nunca datos del lead


def test_sin_clasificador_enriquece_igual_y_no_llama_a_jev(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    _con_icp(admin, busqueda)
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos"))
    caso, _ = _caso(repo, costos, por_lead={lead: MATCH}, jev=False)

    resumen = caso.ejecutar(busqueda)

    assert (resumen.procesados, resumen.clasificados, resumen.sin_clasificar) == (1, 0, 1)
    assert _fila(admin, lead, "enriquecido_en, encaje").encaje is None
    assert [t for t, _, _ in _costos(admin, tenants["a"])] == ["croma_consulta"]


def test_natural_no_se_consulta_en_croma_ni_cambia_de_tipo(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Doña Rosa Gómez", tipo="natural"))
    caso, verificador = _caso(repo, costos)  # si se consultara, sin_match la bajaría a desconocido

    caso.ejecutar(busqueda)

    assert verificador.llamadas == 0 and _costos(admin, tenants["a"]) == []
    assert _fila(admin, lead, "tipo_titular").tipo_titular == "natural"


def test_email_nominal_no_se_guarda_si_hay_telefono(admin, tenants, mundo):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", web="andinos.invalid", tipo="juridica"))
    sitio = {"andinos.invalid": ContactoPublicado(("juan.perez@andinos.invalid",), ((TELEFONO, "sitio_web"),), "ok")}
    caso, _ = _caso(repo, costos, sitio=sitio)

    caso.ejecutar(busqueda)

    f = _fila(admin, lead, "email_cifrado, email_canal, telefono_canal, contactable")
    assert (f.email_cifrado, f.email_canal) == (None, None)  # dato de una persona: no se persiste
    assert (f.telefono_canal, f.contactable) == ("sitio_web", True)


def test_solo_email_nominal_sin_telefono_no_es_contactable(admin, tenants, mundo):
    # Guarda de cumplimiento: el único canal es de una persona, así que ni se guarda ni habilita el contacto.
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", web="andinos.invalid", tipo="juridica"))
    sitio = {"andinos.invalid": ContactoPublicado(("juan.perez@andinos.invalid",), (), "ok")}
    caso, _ = _caso(repo, costos, sitio=sitio)

    resumen = caso.ejecutar(busqueda)

    f = _fila(admin, lead, "email_cifrado, email_canal, telefono_cifrado, contactable, razon_no_contactable")
    assert (f.email_cifrado, f.email_canal, f.telefono_cifrado) == (None, None, None)
    assert (f.contactable, f.razon_no_contactable) == (False, "contacto_nominal")
    assert resumen.contactables == 0


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadError], ids=["connect_error", "read_error"])
def test_jev_con_error_de_transporte_cobra_el_techo_y_sigue(admin, tenants, mundo, error):
    repo, costos, busqueda = mundo
    _con_icp(admin, busqueda)
    leads = [_sembrar(repo, busqueda, _empresa(f"Empresa {i}", tipo="juridica")) for i in range(2)]
    pedidos: list[httpx.Request] = []

    def jev(request):  # el primer pedido se corta en el transporte; el segundo responde bien
        pedidos.append(request)
        if len(pedidos) == 1:
            raise error("sintetico", request=request)
        return httpx.Response(200, json={"salida": {"etiqueta": "encaja", "probabilidad": 0.9}, "uso": {"tokens_in": 7}})
    clasificador = JevClasificador(costos, httpx.MockTransport(jev), "https://jev.invalid/v1/clasificar",
                                   SecretStr("credencial-sintetica"), Decimal("0.042"))
    caso = EnriquecerLead(repo, VerificadorFalso(costos), EnriquecedorFalso(costos), clasificador)

    resumen = caso.ejecutar(busqueda)

    assert (resumen.procesados, resumen.clasificados, resumen.sin_clasificar, resumen.cortado) == (2, 1, 1, False)
    with admin.connect() as c:
        filas = c.execute(text("SELECT lead_id, unidades FROM costos WHERE tenant_id = :t AND tipo = 'jev_tokens'"),
                          {"t": tenants["a"]}).all()
    assert {f.lead_id for f in filas} == set(leads)  # una fila por lead, la del corte incluida
    assert sorted(f.unidades for f in filas) == sorted([Decimal(7), Decimal(len(pedidos[0].content))])  # corte: techo


def test_jev_solo_clasifica_juridicas(admin, tenants, mundo):
    # §2.5: natural y desconocido no son contactables; su nombre (quizás de una persona) no sale hacia jev.
    repo, costos, busqueda = mundo
    _con_icp(admin, busqueda)
    natural = _sembrar(repo, busqueda, _empresa("Doña Rosa Gómez", tipo="natural"))
    desconocido = _sembrar(repo, busqueda, _empresa("Don Pedro Pérez"))  # Croma sin_match: sigue desconocido
    juridica = _sembrar(repo, busqueda, _empresa("Transportes Andinos", tipo="juridica"))
    pedidos: list[httpx.Request] = []

    def jev(request):
        pedidos.append(request)
        return httpx.Response(200, json={"salida": {"etiqueta": "encaja", "probabilidad": 0.9}, "uso": {"tokens_in": 7}})
    clasificador = JevClasificador(costos, httpx.MockTransport(jev), "https://jev.invalid/v1/clasificar",
                                   SecretStr("credencial-sintetica"), Decimal("0.042"))
    caso = EnriquecerLead(repo, VerificadorFalso(costos), EnriquecedorFalso(costos), clasificador)

    resumen = caso.ejecutar(busqueda)

    assert len(pedidos) == 1 and b"Transportes Andinos" in pedidos[0].content  # solo la jurídica
    assert (resumen.procesados, resumen.clasificados, resumen.sin_clasificar) == (3, 1, 2)
    assert {x: _fila(admin, x, "encaje").encaje for x in (natural, desconocido, juridica)} == {
        natural: None, desconocido: None, juridica: "encaja"}
    assert [(t, lead) for t, lead, _ in _costos(admin, tenants["a"]) if t == "jev_tokens"] == [("jev_tokens", juridica)]


EMAIL_OSM = "info@andinos.invalid"  # sintético; lo que T040p guardará al descubrir


def _con_email_osm(admin, cifrador, tenant, lead):
    with admin.begin() as c:
        c.execute(text("UPDATE leads SET email_cifrado = :e, email_canal = 'osm_contacto' WHERE id = :id"),
                  {"e": cifrador.cifrar("email_cifrado", EMAIL_OSM, tenant, lead), "id": lead})


def test_guardar_sin_contacto_no_pisa_el_que_ya_existe(admin, tenants, mundo, cifrador):
    # El UPDATE nunca pone NULL sobre un teléfono o email guardado (COALESCE).
    repo, _, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", tipo="juridica"))
    _con_email_osm(admin, cifrador, tenants["a"], lead)
    with admin.begin() as c:
        c.execute(text("UPDATE leads SET telefono_cifrado = :t, telefono_canal = 'osm_contacto' WHERE id = :id"),
                  {"t": cifrador.cifrar("telefono_cifrado", "+5716000000", tenants["a"], lead), "id": lead})

    repo.guardar_enriquecimiento(lead, ResultadoEnriquecimiento("juridica", None, None, False, "sin_canal_publicado", None))

    f = _fila(admin, lead, "email_cifrado, email_canal, telefono_cifrado, telefono_canal")
    assert (f.email_canal, f.telefono_canal) == ("osm_contacto", "osm_contacto")
    assert cifrador.descifrar("telefono_cifrado", bytes(f.telefono_cifrado), tenants["a"], lead) == "+5716000000"
    assert cifrador.descifrar("email_cifrado", bytes(f.email_cifrado), tenants["a"], lead) == EMAIL_OSM


def test_email_de_osm_se_conserva_si_el_sitio_no_trae_email(admin, tenants, mundo, cifrador):
    repo, costos, busqueda = mundo
    lead = _sembrar(repo, busqueda, _empresa("Transportes Andinos", web="andinos.invalid", tipo="juridica"))
    _con_email_osm(admin, cifrador, tenants["a"], lead)
    caso, _ = _caso(repo, costos, sitio={"andinos.invalid": ContactoPublicado((), (), "ok")})

    resumen = caso.ejecutar(busqueda)

    f = _fila(admin, lead, "email_cifrado, email_canal, contactable, razon_no_contactable")
    assert (f.email_canal, f.contactable, f.razon_no_contactable) == ("osm_contacto", True, None)
    assert cifrador.descifrar("email_cifrado", bytes(f.email_cifrado), tenants["a"], lead) == EMAIL_OSM
    assert resumen.contactables == 1


def test_con_limite_procesa_solo_n_y_dice_cuantos_quedan(mundo):
    """El botón de la API corre por tandas: una petición no puede quedarse minutos bajando sitios web."""
    repo, costos, busqueda = mundo
    for i in range(3):
        _sembrar(repo, busqueda, _empresa(f"Empresa {i} SAS", tipo="juridica"))
    caso, _ = _caso(repo, costos, jev=False)

    primera = caso.ejecutar(busqueda, limite=2)
    segunda = caso.ejecutar(busqueda, limite=2)

    assert (primera.procesados, primera.pendientes) == (2, 1)
    assert (segunda.procesados, segunda.pendientes) == (1, 0)
