"""Raíz de composición compartida por la CLI y la API: qué fuentes se arman y cómo se arma cada una.

Es el único lugar (junto con `app.cli` y `app.main`) que une descubrimiento con la infraestructura de costos.
"""
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import yaml

from app.config import Settings
from app.modulos.calificacion.infraestructura.dapta_csv import DaptaCSV
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.aplicacion.camaras import cargar_camaras
from app.modulos.descubrimiento.aplicacion.registro import Registro, cargar_registro
from app.modulos.descubrimiento.dominio.modelos import MetaFuente
from app.modulos.descubrimiento.dominio.puertos import (
    FabricaFuentes,
    FuenteDescubrimiento,
)
from app.modulos.intake.infraestructura.llm.interpretador_claude import (
    InterpretadorClaude,
)
from app.modulos.intake.infraestructura.llm.interpretador_openrouter import (
    URL_BASE as URL_OPENROUTER,
)
from app.modulos.intake.infraestructura.llm.interpretador_openrouter import (
    InterpretadorOpenRouter,
)

CONFIG = Path(__file__).resolve().parents[1] / "config"


def cargar_tarifas(ruta: Path = CONFIG / "tarifas.yaml") -> dict[str, Decimal]:
    """Tarifa unitaria por proveedor desde tarifas.yaml; cada valor pasa por str para no arrastrar el error del float.

    `dapta` puede faltar (`null`): se lee como `None`, nunca como `Decimal(0)` (TarifaPendiente lo distingue)."""
    t = yaml.safe_load(ruta.read_text())
    usd_por_minuto = t["dapta"]["usd_por_minuto"]
    return {"croma": Decimal(str(t["croma"]["usd_por_credito"])), "osm": Decimal(str(t["computo_seg_usd"])),
            "datos.gov.co": Decimal(str(t["computo_seg_usd"])), "web_fetch": Decimal(str(t["web_fetch_usd"])),
            "jev_in_por_M": Decimal(str(t["jev"]["in_usd_por_M"])),
            "dapta": Decimal(str(usd_por_minuto)) if usd_por_minuto is not None else None}


def cargar_tarifas_llm() -> dict[str, dict[str, Decimal]]:
    """modelo -> {in_usd_por_M, out_usd_por_M} desde tarifas.yaml. Decimal(str(v)): el float 0.10 arrastra error al costo."""
    llm = yaml.safe_load((CONFIG / "tarifas.yaml").read_text()).get("llm") or {}
    return {modelo: {k: Decimal(str(v)) for k, v in t.items()} for modelo, t in llm.items()}


# Proveedores de la Puerta B: mismo puerto (GeneradorEstructurado), un adaptador cada uno. Se elige con IA_PROVEEDOR.
URL_IA = {"anthropic": "https://api.anthropic.com", "openrouter": URL_OPENROUTER}


def _proveedor(ajustes) -> str:
    return (getattr(ajustes, "ia_proveedor", None) or "anthropic").strip().lower()


def ia_configurada(ajustes, tarifas_llm: Mapping[str, Mapping]) -> bool:
    """Key + modelo + tarifa de ese modelo + proveedor conocido. Cualquier falta = la Puerta B no está disponible.
    La tarifa se busca por IA_MODELO (el nombre del libro de costos), no por el nombre que usa el proveedor."""
    key, modelo = ajustes.ia_api_key, (ajustes.ia_modelo or "").strip()
    return bool(key and key.get_secret_value().strip() and modelo in tarifas_llm and _proveedor(ajustes) in URL_IA)


def generador_de_frase(ajustes, tarifas_llm: Mapping[str, Mapping], costos: RegistroCostos,
                       transporte: httpx.BaseTransport, codigos_ciiu=None) -> InterpretadorClaude | InterpretadorOpenRouter | None:
    """El adaptador de la Puerta B atado a este tenant (por `costos`), o None si la IA no está disponible."""
    if not ia_configurada(ajustes, tarifas_llm):
        return None
    modelo = ajustes.ia_modelo.strip()
    proveedor = _proveedor(ajustes)
    http = httpx.Client(base_url=URL_IA[proveedor], transport=transporte, timeout=30)
    clave, tarifa = ajustes.ia_api_key.get_secret_value(), dict(tarifas_llm[modelo])
    if proveedor == "openrouter":
        nombre = (getattr(ajustes, "ia_modelo_proveedor", None) or modelo).strip()
        return InterpretadorOpenRouter(costos, tarifa, nombre, clave, http, codigos_ciiu=codigos_ciiu)
    return InterpretadorClaude(costos, tarifa, modelo, clave, http, codigos_ciiu=codigos_ciiu)


def registro_api(ruta_yaml: Path, catalogo: dict[str, type]) -> Registro:
    """El registro que arma la API. Croma (de pago) entra porque el tope de gasto está aplicado: `EjecutarBorrador` corta
    con `TopeExcedido` antes de la llamada que lo pasaría (guardas en tests/unit/api/test_composicion.py). Sin
    CROMA_API_KEY, `app.main` no lo pone en el catálogo y queda como `sin_implementacion`."""
    return cargar_registro(ruta_yaml, catalogo)


def armador_de_fuente(
    clase: type, meta: MetaFuente, *, ajustes: Callable[[], Settings], costos: RegistroCostos,
    tarifas: Mapping[str, Decimal], limites: Mapping, api_key, transporte: Callable[[], httpx.BaseTransport],
    camaras_yaml: Callable[[], Path] = lambda: CONFIG / "camaras_co.yaml",
) -> Callable[[UUID], FuenteDescubrimiento]:
    """lote_id -> la fuente armada para esa búsqueda. `transporte` y `ajustes` se llaman al armar, no antes."""
    def armar(lote_id: UUID):
        if meta.proveedor == "datos.gov.co":
            extra = {}
            if ajustes().datos_gov_co_url:
                extra["url"] = ajustes().datos_gov_co_url
            token = ajustes().datos_gov_co_app_token
            return clase(
                transporte=transporte(), reloj=lambda: datetime.now(UTC), monotonico=time.monotonic,
                dormir=time.sleep, costos=costos, cache=None,
                camaras=cargar_camaras(camaras_yaml()),
                tarifas={"computo_seg_usd": tarifas["datos.gov.co"]}, lote_id=lote_id, meta=meta,
                app_token=token.get_secret_value() if token else None, **extra,
            )
        kwargs = {"meta": meta, "registro_costos": costos, "transporte": transporte(), "lote_id": lote_id}
        if meta.proveedor in tarifas:
            kwargs["costo_unitario"] = tarifas[meta.proveedor]
        if meta.proveedor == "osm":
            kwargs["repo_url"] = ajustes().repo_url
            if ajustes().overpass_url:
                kwargs["url"] = ajustes().overpass_url
        elif meta.proveedor == "croma":
            kwargs.update(api_key=api_key.get_secret_value(), limites=limites)
            if ajustes().croma_base_url:
                kwargs["url"] = ajustes().croma_base_url
        return clase(**kwargs)
    return armar


def fabrica_de_fuentes(registro: Registro, **comunes) -> FabricaFuentes:
    """FabricaFuentes para la API: `lote_id` -> todas las fuentes del registro, atadas a ese lote."""
    armadores = {clave: armador_de_fuente(clase, meta, **comunes) for clave, (clase, meta) in registro.fuentes.items()}
    return lambda lote_id: {clave: armar(lote_id) for clave, armar in armadores.items()}


def cargar_geografia(carpeta: Path) -> dict[str, dict]:
    """pais -> contenido de su archivo en config/geografia/. Dos archivos del mismo país, o uno sin `pais`, impiden arrancar."""
    archivos: dict[str, dict] = {}
    for ruta in sorted(carpeta.glob("*.yaml")):
        contenido = yaml.safe_load(ruta.read_text()) or {}
        pais = contenido.get("pais")
        if not pais:
            raise ValueError(f"{ruta.name}: falta `pais`")
        if pais in archivos:
            raise ValueError(f"geografía duplicada para {pais}: {ruta.name}")
        archivos[pais] = contenido
    return archivos


def calificador_api(ruta_yaml: Path):
    """`DaptaCSV` si `calificadores.dapta_csv.habilitado` en fuentes.yaml; si no, None (el import responde 503)."""
    calificadores = (yaml.safe_load(ruta_yaml.read_text()) or {}).get("calificadores") or {}
    return DaptaCSV() if (calificadores.get("dapta_csv") or {}).get("habilitado") else None
