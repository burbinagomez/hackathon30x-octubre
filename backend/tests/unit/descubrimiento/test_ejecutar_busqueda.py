from datetime import UTC, datetime

import pytest

from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBusqueda
from app.modulos.descubrimiento.dominio.errores import FuenteNoDisponible, LimiteFuenteAgotado
from app.modulos.descubrimiento.dominio.modelos import Actividad, CriteriosICP, EmpresaCruda, MetaFuente
from tests.falsos import FuenteFalsa, RegistroCostosFalso, RepositorioLeadsFalso

AS_OF = datetime(2026, 10, 1, tzinfo=UTC)
ICP_CO = CriteriosICP(pais="CO", filtros={"ciiu": "4711"})


def _meta(clave, paises=frozenset({"CO"})):
    return MetaFuente(clave=clave, proveedor=f"prov_{clave}", paises=paises, filtros=frozenset({"ciiu"}),
                      trae=frozenset({"id_fiscal"}), tipo="live", licencia=f"lic_{clave}")


def _empresa(fuente, nit="900123456", pais="CO"):
    return EmpresaCruda(pais=pais, nombre="ACME SAS", fuente=fuente, url_origen=f"https://{fuente}.test/acme",
                        as_of=AS_OF, actividad=Actividad("4711", "CIIU"), id_fiscal=nit, tipo_titular="juridica")


def _caso(repo, costos, por_fuente, errores=None, paises=frozenset({"CO"})):
    """por_fuente: clave -> empresas. Devuelve el caso de uso y la lista de lote_id con que se armó cada fuente."""
    errores = errores or {}
    armadas = []

    def fabrica(clave):
        def armar(lote_id):
            armadas.append((clave, lote_id))
            return FuenteFalsa(_meta(clave, paises), costos, lote_id, tuple(por_fuente[clave]), errores.get(clave))
        return armar

    fuentes = {clave: (_meta(clave, paises), fabrica(clave)) for clave in por_fuente}
    return EjecutarBusqueda(repo, fuentes), armadas


def test_mismo_nit_de_dos_fuentes_queda_en_un_lead():
    repo = RepositorioLeadsFalso()
    caso, _ = _caso(repo, RegistroCostosFalso(), {"f1": [_empresa("f1")], "f2": [_empresa("f2")]})
    caso.ejecutar(ICP_CO)
    assert len(repo.leads) == 1
    assert len(repo.lead_fuentes) == 2


def test_misma_fuente_repetida_no_duplica_lead_fuentes():
    repo = RepositorioLeadsFalso()
    caso, _ = _caso(repo, RegistroCostosFalso(), {"f1": [_empresa("f1"), _empresa("f1")]})
    caso.ejecutar(ICP_CO)
    assert len(repo.leads) == 1
    assert len(repo.lead_fuentes) == 1


def test_nit_con_y_sin_formato_es_el_mismo_lead():
    repo = RepositorioLeadsFalso()
    caso, _ = _caso(repo, RegistroCostosFalso(),
                    {"f1": [_empresa("f1", nit="900.123.456-7")], "f2": [_empresa("f2", nit="900123456")]})
    caso.ejecutar(ICP_CO)
    assert list(repo.leads) == [("CO", "900123456")]


def test_mismo_nit_distinto_pais_son_dos_leads():
    repo = RepositorioLeadsFalso()
    caso, _ = _caso(repo, RegistroCostosFalso(),
                    {"f1": [_empresa("f1", pais="CO"), _empresa("f1", pais="PE")]}, paises=frozenset({"*"}))
    caso.ejecutar(ICP_CO)
    assert set(repo.leads) == {("CO", "900123456"), ("PE", "900123456")}


def test_lead_existente_en_segunda_busqueda_no_duplica_cumplimiento():
    repo = RepositorioLeadsFalso()
    caso, _ = _caso(repo, RegistroCostosFalso(), {"f1": [_empresa("f1")]})
    primera = caso.ejecutar(ICP_CO)
    segunda = caso.ejecutar(ICP_CO)
    assert len(repo.leads) == 1
    assert len(repo.cumplimiento) == 1
    assert {b for _, _, b in repo.lead_fuentes} == {primera.busqueda_id, segunda.busqueda_id}


def test_cada_lead_nuevo_tiene_fila_en_cumplimiento():
    repo = RepositorioLeadsFalso()
    caso, _ = _caso(repo, RegistroCostosFalso(), {"f1": [_empresa("f1", nit="900123456"), _empresa("f1", nit="800111222")]})
    caso.ejecutar(ICP_CO)
    assert len(repo.leads) == 2
    assert sorted(repo.cumplimiento.values()) == [("f1", "lic_f1", "https://f1.test/acme", AS_OF)] * 2


def test_sin_fuente_para_el_pais_se_reporta():
    repo = RepositorioLeadsFalso()
    caso, armadas = _caso(repo, RegistroCostosFalso(), {"f1": [_empresa("f1")]})
    icp_br = CriteriosICP(pais="BR", filtros={"ciiu": "4711"})
    resultado = caso.ejecutar(icp_br)
    assert resultado.sin_fuente_para == ("BR", icp_br.filtros)
    assert repo.leads == {}
    assert armadas == []
    assert repo.busquedas == {resultado.busqueda_id: "terminada"}


def test_cada_fuente_se_arma_con_lote_id_igual_a_busqueda_id():
    repo, costos = RepositorioLeadsFalso(), RegistroCostosFalso()
    caso, armadas = _caso(repo, costos, {"f1": [_empresa("f1")], "f2": [_empresa("f2", nit="800111222")]})
    resultado = caso.ejecutar(ICP_CO)
    assert set(repo.busquedas) == {resultado.busqueda_id}
    assert sorted(armadas) == [("f1", resultado.busqueda_id), ("f2", resultado.busqueda_id)]
    assert len(costos.filas) == 2
    assert {f.lote_id for f in costos.filas} == {resultado.busqueda_id}


@pytest.mark.parametrize("error", [LimiteFuenteAgotado("cupo"), FuenteNoDisponible("502")], ids=lambda e: type(e).__name__)
def test_error_de_fuente_se_reporta_y_busqueda_queda_con_errores(error):
    repo = RepositorioLeadsFalso()
    caso, _ = _caso(repo, RegistroCostosFalso(), {"rota": [], "sana": [_empresa("sana")]}, errores={"rota": error})
    resultado = caso.ejecutar(ICP_CO)
    assert resultado.errores == {"rota": error}
    assert list(repo.leads) == [("CO", "900123456")]  # la fuente sana sigue
    assert repo.busquedas == {resultado.busqueda_id: "con_errores"}
