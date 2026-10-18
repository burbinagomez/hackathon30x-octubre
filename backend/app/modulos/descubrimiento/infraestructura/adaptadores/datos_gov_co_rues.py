import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.aplicacion.camaras import Camara, camaras_de
from app.modulos.descubrimiento.dominio.errores import CriterioNoSoportado
from app.modulos.descubrimiento.dominio.modelos import (
    Actividad,
    CriteriosICP,
    EmpresaCruda,
    MetaFuente,
    PaginaEmpresas,
)

# Dataset público de Confecámaras en datos.gov.co. El override (stub, D9) llega desde settings por la fábrica.
URL_DATASET = "https://www.datos.gov.co/resource/c82u-588k.json"

LIMITE_FILAS = 5000
TIMEOUT_SEG = 30.0
# Lista blanca: nunca se piden nombres, apellidos ni representante legal (principio VII).
SELECT_FILAS = (
    "nit,digito_verificacion,razon_social,cod_ciiu_act_econ_pri,"
    "codigo_camara,organizacion_juridica,fecha_renovacion"
)
_CIIU = re.compile(r"\d{4}")
_NIT = re.compile(r"\d{9}")


def _es_juridica_valida(fila: Mapping[str, Any]) -> bool:
    """Defensa en profundidad: el servidor ya filtró; acá se descarta lo que no debió llegar."""
    organizacion = fila.get("organizacion_juridica")
    nit = fila.get("nit")
    nombre = fila.get("razon_social")
    return (
        isinstance(organizacion, str)
        and organizacion.strip() != ""
        and organizacion.strip().upper() != "PERSONA NATURAL"
        and isinstance(nit, str)
        and _NIT.fullmatch(nit.strip()) is not None
        and isinstance(nombre, str)
        and nombre.strip() != ""
    )


class DatosGovCoRues:
    def __init__(
        self,
        *,
        transporte: httpx.BaseTransport,
        reloj: Callable[[], datetime],
        dormir: Callable[[float], None],
        costos: RegistroCostos,
        cache: Any | None,  # puerto de caché de la 002; None en el mínimo
        camaras: Mapping[str, Camara],
        tarifas: Mapping[str, Any],
        lote_id: UUID | None,
        meta: MetaFuente,
        url: str = URL_DATASET,
        app_token: str | None = None,
    ) -> None:
        self._transporte = transporte
        self._reloj = reloj
        self._dormir = dormir
        self._costos = costos
        self._cache = cache
        self._camaras = camaras
        self._tarifas = tarifas
        self._lote_id = lote_id
        self.meta = meta
        self._url = url
        self._app_token = app_token

    def _validar(self, criterios: CriteriosICP) -> tuple[str, list[str]]:
        ciiu = criterios.filtros.get("ciiu")
        if not isinstance(ciiu, str) or _CIIU.fullmatch(ciiu) is None:
            raise CriterioNoSoportado(f"{self.meta.clave}: ciiu debe ser de 4 dígitos")
        departamento = criterios.filtros.get("departamento")
        if not isinstance(departamento, str):
            raise CriterioNoSoportado(f"{self.meta.clave}: falta departamento")
        codigos = sorted(camaras_de(dict(self._camaras), departamento))
        if not codigos:
            raise CriterioNoSoportado(f"{self.meta.clave}: departamento sin cámaras")
        return ciiu, codigos

    def buscar(self, criterios: CriteriosICP, pagina: int) -> PaginaEmpresas:
        ciiu, codigos = self._validar(criterios)
        if pagina > 1:  # una sola página: sin $order no hay $offset estable
            return PaginaEmpresas(empresas=(), total=None)
        enlista = ",".join(f"'{c}'" for c in codigos)  # códigos del YAML, nunca texto libre
        where = (
            "organizacion_juridica != 'PERSONA NATURAL'"
            " AND organizacion_juridica IS NOT NULL"
            " AND estado_matricula = 'ACTIVA'"
            f" AND cod_ciiu_act_econ_pri = '{ciiu}'"
            f" AND codigo_camara in({enlista})"
            " AND nit IS NOT NULL"
        )
        cabeceras = {"X-App-Token": self._app_token} if self._app_token else {}
        with httpx.Client(transport=self._transporte, timeout=TIMEOUT_SEG, headers=cabeceras) as cliente:
            respuesta = cliente.get(
                self._url, params={"$select": SELECT_FILAS, "$where": where, "$limit": str(LIMITE_FILAS)}
            )
        respuesta.raise_for_status()
        as_of = self._reloj()
        empresas = tuple(
            EmpresaCruda(
                pais="CO",
                nombre=fila["razon_social"].strip(),
                fuente=self.meta.clave,
                url_origen=f"{self._url}?nit={fila['nit'].strip()}",
                as_of=as_of,
                actividad=Actividad(ciiu, "CIIU"),
                id_fiscal=fila["nit"].strip(),  # sin DV
                tipo_titular="juridica",  # solo para filas que pasan _es_juridica_valida
                ciudad=self._ciudad(fila.get("codigo_camara")),
            )
            for fila in respuesta.json()
            if _es_juridica_valida(fila)
        )
        return PaginaEmpresas(empresas=empresas, total=None)

    def _ciudad(self, codigo: Any) -> str | None:
        camara = self._camaras.get(str(codigo))
        return camara.municipio_sede if camara else None
