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
from app.modulos.enriquecimiento.dominio.puertos import BuscadorRazonSocialRues, CoincidenciaRues, VerificacionTitular

FUENTE = "datos_gov_co_rues"
DATASET = "c82u-588k"


def _desconocido(motivo: str, candidatos: int | None = None) -> VerificacionTitular:
    return VerificacionTitular("desconocido", motivo, ConstanciaTitular(motivo, FUENTE, DATASET, candidatos=candidatos))


class RuesDatosGov:
    def __init__(self, buscador: BuscadorRazonSocialRues, municipio_de_camara: Mapping[str, str],
                 alias_ciudad: Mapping[str, str] | None = None) -> None:
        """`municipio_de_camara`: codigo_camara -> municipio sede (el dataset no trae municipio, ver camaras_co.yaml).
        `alias_ciudad`: nombre corto normalizado -> sede normalizada ("CALI" -> "SANTIAGO DE CALI")."""
        self._buscador = buscador
        self._municipios = municipio_de_camara
        self._alias = alias_ciudad or {}

    def verificar(self, lead_id: UUID, nombre_normalizado: str, ciudad: str | None, pais: str) -> VerificacionTitular:
        if pais != "CO":  # el RUES es colombiano: una ciudad que coincida en otro país no prueba nada
            return _desconocido("pais_no_soportado")
        nombre = normalizar_nombre(nombre_normalizado)
        ciudad_lead = normalizar_ciudad(ciudad or "")
        ciudad_lead = self._alias.get(ciudad_lead, ciudad_lead)
        if not ciudad_lead:  # sin ciudad no hay segundo dato que desambigüe: ni se consulta
            return _desconocido("sin_ciudad")
        if not nombre:
            return _desconocido("sin_match")
        contexto = ContextoCosto(None, None, lead_id)
        try:
            busqueda = self._buscador.buscar_homonimas(nombre, contexto)
        except FuenteNoDisponible:  # solo la clave y el status: el mensaje de la fuente no lleva el nombre
            return _desconocido("fuente_no_disponible")
        candidatas = list(busqueda.coincidencias)
        if busqueda.truncada:
            return _desconocido("ambiguo")
        # Varias matrículas del mismo NIT son una sola empresa. El servidor ya filtra
        # activas y jurídicas; acá se revisa igual, y una natural que llegue con el mismo nombre en la misma ciudad se cuenta.
        exactas: dict[str, tuple[CoincidenciaRues, str]] = {}  # NIT -> (fila, municipio)
        naturales_en_respuesta = 0
        for c in candidatas:
            municipio = self._municipios.get(c.camara or "")
            if not (c.razon_social and normalizar_nombre(c.razon_social) == nombre
                    and municipio is not None and normalizar_ciudad(municipio) == ciudad_lead):
                continue
            organizacion = (c.organizacion_juridica or "").strip().upper()
            if organizacion == "PERSONA NATURAL":
                naturales_en_respuesta += 1
            elif organizacion and (c.estado_matricula or "").strip().upper() == "ACTIVA":
                exactas.setdefault(c.nit, (c, municipio))
        if naturales_en_respuesta:
            return VerificacionTitular("desconocido", "ambiguo", ConstanciaTitular(
                "ambiguo", FUENTE, DATASET, naturales_homonimas=naturales_en_respuesta))
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
        (nit, (c, municipio)), = exactas.items()
        return VerificacionTitular("juridica", "match_unico", ConstanciaTitular(
            "match_unico", FUENTE, DATASET, nit=nit, razon_social=c.razon_social, municipio_sede_camara=municipio,
            codigo_camara=c.camara, organizacion_juridica=c.organizacion_juridica.strip(),
            estado_matricula=c.estado_matricula.strip().upper()))
