"""VerificadorTitular real: nombre + ciudad contra el RUES de datos.gov.co (enmienda 2026-10-18 de la spec 006).

Decisión de cumplimiento del dueño: "Sí, nombre + ciudad". Es jurídica solo si el nombre normalizado coincide EXACTO con
una sola empresa (un solo NIT) del RUES, activa, en la misma ciudad. Todo lo demás falla cerrado a `desconocido`.

No habla HTTP ni escribe costos: pide al cliente del RUES de la 011 (`BuscadorRazonSocialRues`), que cobra cada request
con el `lead_id` del contexto antes de devolver. Nada de acá loguea el nombre del lead.
"""
from collections.abc import Mapping
from uuid import UUID

from app.modulos.costos.dominio.modelos import ContextoCosto
from app.modulos.descubrimiento.dominio.errores import FuenteNoDisponible
from app.modulos.descubrimiento.dominio.modelos import ConstanciaTitular
from app.modulos.enriquecimiento.dominio.normalizar_titular import normalizar_ciudad, normalizar_nombre
from app.modulos.enriquecimiento.dominio.puertos import BuscadorRazonSocialRues, VerificacionTitular

FUENTE = "datos_gov_co_rues"
DATASET = "c82u-588k"


def _desconocido(motivo: str, candidatos: int | None = None) -> VerificacionTitular:
    return VerificacionTitular("desconocido", motivo, ConstanciaTitular(motivo, FUENTE, DATASET, candidatos=candidatos))


class RuesDatosGov:
    def __init__(self, buscador: BuscadorRazonSocialRues, municipio_de_camara: Mapping[str, str], tope: int) -> None:
        """`municipio_de_camara`: codigo_camara -> municipio sede (el dataset no trae municipio, ver camaras_co.yaml).
        `tope`: filas con las que el cliente corta; una respuesta que lo alcanza pudo dejar fuera un segundo candidato."""
        self._buscador = buscador
        self._municipios = municipio_de_camara
        self._tope = tope

    def verificar(self, lead_id: UUID, nombre_normalizado: str, ciudad: str | None) -> VerificacionTitular:
        nombre = normalizar_nombre(nombre_normalizado)
        ciudad_lead = normalizar_ciudad(ciudad or "")
        if not ciudad_lead:  # sin ciudad no hay segundo dato que desambigüe: ni se consulta
            return _desconocido("sin_ciudad")
        if not nombre:
            return _desconocido("sin_match")
        contexto = ContextoCosto(None, None, lead_id)
        try:
            candidatas = list(self._buscador.buscar_coincidencias(nombre, contexto))
        except FuenteNoDisponible:  # solo la clave y el status: el mensaje de la fuente no lleva el nombre
            return _desconocido("fuente_no_disponible")
        if len(candidatas) >= self._tope:
            return _desconocido("ambiguo")
        # NIT -> (razón social, municipio): varias matrículas del mismo NIT son una sola empresa.
        exactas: dict[str, tuple[str, str]] = {}
        for c in candidatas:
            municipio = self._municipios.get(c.camara or "")
            if (c.razon_social and normalizar_nombre(c.razon_social) == nombre
                    and municipio is not None and normalizar_ciudad(municipio) == ciudad_lead):
                exactas.setdefault(c.nit, (c.razon_social, municipio))
        if not exactas:
            return _desconocido("sin_match")
        if len(exactas) > 1:
            return _desconocido("ambiguo", candidatos=len(exactas))
        # Una persona natural con ese nombre en la cámara de la ciudad: no se puede afirmar que el lead sea la SAS. El
        # servidor excluye a las naturales de la búsqueda, así que se cuentan aparte (solo el número).
        camaras = [codigo for codigo, m in self._municipios.items() if normalizar_ciudad(m) == ciudad_lead]
        try:
            naturales = self._buscador.contar_naturales(nombre, camaras, contexto)
        except FuenteNoDisponible:
            return _desconocido("fuente_no_disponible")
        if naturales > 0:
            return VerificacionTitular("desconocido", "ambiguo", ConstanciaTitular(
                "ambiguo", FUENTE, DATASET, naturales_homonimas=naturales))
        (nit, (razon_social, municipio)), = exactas.items()
        return VerificacionTitular("juridica", "match_unico", ConstanciaTitular(
            "match_unico", FUENTE, DATASET, nit=nit, razon_social=razon_social, municipio=municipio))
