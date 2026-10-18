"""Spec 015: resultado por fuente. Una fuente que falla (con lo que sea) o no encuentra no frena a las demás, y la respuesta
dice, fuente por fuente, qué pasó. Estados como códigos; el texto es del front."""
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBorrador
from app.modulos.descubrimiento.dominio.errores import (
    CriterioNoSoportado,
    ErrorPersistencia,
    FuenteNoDisponible,
    LimiteFuenteAgotado,
)
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda, MetaFuente
from tests.falsos import FabricaFalsa, RegistroCostosFalso, RepositorioLeadsFalso

AS_OF = datetime(2026, 10, 1, tzinfo=UTC)
A, B = "fuente_a", "fuente_b"
ICP = CriteriosICP(pais="CO", filtros={"ciiu": "1081", "departamento": "73"})


def _meta(clave, costo=Decimal(0)):
    return MetaFuente(clave=clave, proveedor=clave, paises=frozenset({"CO"}), filtros=frozenset({"ciiu", "departamento"}),
                      trae=frozenset({"nombre"}), tipo="live", licencia=f"lic_{clave}", costo_maximo_llamada=costo)


def _empresa(fuente, nit):
    return EmpresaCruda(pais="CO", nombre=f"EMPRESA {nit} SAS", fuente=fuente, url_origen=f"https://{fuente}.test/{nit}",
                        as_of=AS_OF, actividad=Actividad("1081", "CIIU"), id_fiscal=nit, tipo_titular="juridica")


def _tres(fuente):
    return tuple(_empresa(fuente, f"90000000{i}") for i in (1, 2, 3))


def _caso(empresas=None, errores=None, repo=None, tope=Decimal("5"), metas=None, gasto=None):
    repo, costos = repo or RepositorioLeadsFalso(), RegistroCostosFalso()
    metas = metas or {A: _meta(A), B: _meta(B)}
    fabrica = FabricaFalsa(costos, metas, empresas or {}, errores, gasto)
    borrador_id = repo.crear_borrador(ICP, "email", tope, None)
    return EjecutarBorrador(repo, fabrica, {}, costos), repo, borrador_id


def test_excepcion_inesperada_en_una_fuente_no_tumba_a_las_demas():
    caso, repo, borrador_id = _caso(empresas={B: _tres(B)}, errores={A: ValueError("bug raro")})

    r = caso.ejecutar(borrador_id)  # no lanza

    assert repo.busquedas[borrador_id] == "completada"
    assert len(repo.leads) == 3
    assert {k: (v.estado, v.encontrados) for k, v in r.por_fuente.items()} == {A: ("no_disponible", 0), B: ("con_resultados", 3)}
    assert (r.encontrados, r.nuevos) == (3, 3)  # lo de la fuente caída no suma


def test_todas_fallan_da_error_sin_500():
    caso, repo, borrador_id = _caso(errores={A: ValueError("x"), B: KeyError("y")})

    r = caso.ejecutar(borrador_id)  # no lanza: la API responde 200 con estado `error`

    assert repo.busquedas[borrador_id] == "error"
    assert {k: v.estado for k, v in r.por_fuente.items()} == {A: "no_disponible", B: "no_disponible"}
    assert set(r.errores) == {A, B}  # el error no se traga: viaja en el resultado
    assert repo.leads == {}


def test_fuente_sin_empresas_es_sin_resultados_no_error():
    caso, repo, borrador_id = _caso(empresas={A: (), B: _tres(B)})

    r = caso.ejecutar(borrador_id)

    assert repo.busquedas[borrador_id] == "completada"
    assert {k: (v.estado, v.encontrados) for k, v in r.por_fuente.items()} == {A: ("sin_resultados", 0), B: ("con_resultados", 3)}
    assert r.errores == {}  # no es un error


def test_todas_sin_resultados_es_completada():
    caso, repo, borrador_id = _caso(empresas={A: (), B: ()})

    caso.ejecutar(borrador_id)

    assert repo.busquedas[borrador_id] == "completada"  # respondieron: cero no es falla


def test_cada_error_conocido_tiene_su_estado():
    metas = {c: _meta(c) for c in (A, B, "fuente_c")}
    caso, repo, borrador_id = _caso(metas=metas, errores={A: CriterioNoSoportado("x"), B: FuenteNoDisponible("y"),
                                                         "fuente_c": RuntimeError("z")})

    r = caso.ejecutar(borrador_id)

    assert {k: v.estado for k, v in r.por_fuente.items()} == {A: "no_soporta_criterio", B: "no_disponible",
                                                             "fuente_c": "no_disponible"}


def test_falla_al_persistir_una_fuente_deshace_solo_esa():
    # A trae 2 empresas y la segunda no se puede guardar: ni la primera de A queda. B no se entera.
    repo = RepositorioLeadsFalso(falla_si=lambda e: e.id_fiscal == "900000002" and e.fuente == A)
    caso, repo, borrador_id = _caso(empresas={A: _tres(A)[:2], B: _tres(B)[2:]}, repo=repo)

    r = caso.ejecutar(borrador_id)

    assert {k: (v.estado, v.encontrados) for k, v in r.por_fuente.items()} == {A: ("no_disponible", 0), B: ("con_resultados", 1)}
    assert list(repo.leads) == [("CO", "900000003")]
    assert {fuente for _, fuente, _ in repo.lead_fuentes} == {B}
    assert len(repo.cumplimiento) == 1
    assert repo.busquedas[borrador_id] == "completada"
    assert isinstance(r.errores[A], ErrorPersistencia)


def test_omitida_por_tope_y_limite_agotado_aparecen_en_por_fuente():
    metas = {c: _meta(c, Decimal("0.5")) for c in (A, B, "fuente_c")}
    # Peor caso 1.5 <= tope 1.6, pero B termina costando 1.5 de verdad: C ya no cabe y no se llama.
    caso, repo, borrador_id = _caso(metas=metas, tope=Decimal("1.6"), empresas={B: _tres(B)},
                                    errores={A: LimiteFuenteAgotado("429")}, gasto={B: Decimal("1.5")})

    r = caso.ejecutar(borrador_id)

    assert {k: (v.estado, v.encontrados) for k, v in r.por_fuente.items()} == {
        A: ("limite_agotado", 0), B: ("con_resultados", 3), "fuente_c": ("omitida_por_tope", 0)}
    assert repo.busquedas[borrador_id] == "tope_alcanzado"


def test_fuentes_no_seleccionadas_no_aparecen():
    metas = {A: _meta(A), B: MetaFuente(clave=B, proveedor=B, paises=frozenset({"MX"}), filtros=frozenset({"ciiu", "departamento"}),
                                        trae=frozenset({"nombre"}), tipo="live", licencia="l")}
    caso, repo, borrador_id = _caso(metas=metas, empresas={A: _tres(A)})

    r = caso.ejecutar(borrador_id)

    assert set(r.por_fuente) == {A}


def test_el_log_de_una_fuente_caida_lleva_clave_y_clase_nunca_el_mensaje(caplog):
    caso, _, borrador_id = _caso(empresas={B: _tres(B)}, errores={A: ValueError("ACME SAS 900123456 https://x.test/?k=secreto")})

    with caplog.at_level(logging.DEBUG):
        caso.ejecutar(borrador_id)

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert A in texto and "ValueError" in texto
    assert "ACME" not in texto and "secreto" not in texto and "900123456" not in texto
    assert all(r.exc_info is None and r.exc_text is None for r in caplog.records)  # el traceback también trae el mensaje


def test_el_log_de_una_fuente_caida_lleva_el_codigo_http_y_nada_mas_del_mensaje(caplog):
    # En prod solo se veía "FuenteNoDisponible": sin el código no se sabe si es 429, 401 o timeout.
    caso, _, borrador_id = _caso(empresas={B: _tres(B)},
                                 errores={A: FuenteNoDisponible("croma: http 401 ACME SAS 900123456")})

    with caplog.at_level(logging.DEBUG):
        caso.ejecutar(borrador_id)

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "detalle=http 401" in texto
    assert "ACME" not in texto and "900123456" not in texto
