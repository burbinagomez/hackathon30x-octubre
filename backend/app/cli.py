"""Raíz de composición: único módulo que une descubrimiento con la infraestructura de costos."""
import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from uuid import UUID

import httpx
import yaml
from pydantic import ValidationError

from app.composicion import CONFIG, adaptadores_enriquecer, armador_de_fuente, cargar_tarifas
from app.config import Settings
from app.modulos.costos.dominio.modelos import OperacionCosto
from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBusqueda
from app.modulos.descubrimiento.aplicacion.registro import cargar_actividades, cargar_registro
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.dominio.puertos import RepositorioLeads
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo



@dataclass(frozen=True)
class Persistencia:
    repo: RepositorioLeads
    costos: RegistroCostos


class _ContadorDeCreditos:
    """Delega en el libro y suma las unidades de Croma que se registran en esta corrida (el puerto no expone el lote)."""

    def __init__(self, costos: RegistroCostos):
        self._costos = costos
        self.creditos = Decimal(0)

    def registrar(self, op: OperacionCosto) -> None:
        self._costos.registrar(op)
        if op.proveedor == "croma":
            self.creditos += op.unidades

    def requests_24h(self, proveedor: str) -> int:
        return self._costos.requests_24h(proveedor)

    def creditos_mes(self, proveedor: str) -> Decimal:
        return self._costos.creditos_mes(proveedor)


def _persistencia_postgres(settings: Settings, tenant: UUID) -> Persistencia:
    from app import db
    from app.seguridad.cifrado import Cifrador
    from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
    from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

    engine = db.crear_engine(settings.database_url)
    return Persistencia(RepositorioLeadsPostgres(engine, tenant, Cifrador(settings.cifrado_key.get_secret_value())), PostgresCostos(engine, tenant))


def _adaptadores_enriquecer(ajustes: Settings, costos: RegistroCostos, tarifas: dict[str, Decimal]):
    return adaptadores_enriquecer(ajustes, costos, tarifas, httpx.HTTPTransport())


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="comando", required=True)
    b = sub.add_parser("buscar", help="Busca empresas que cumplen el ICP en las fuentes habilitadas.")
    b.add_argument("--tenant", type=UUID, required=True)
    b.add_argument("--pais", required=True)
    b.add_argument("--ciiu")
    b.add_argument("--departamento")
    b.add_argument("--ciudad")
    e = sub.add_parser("enriquecer", help="Enriquece los leads de una búsqueda que todavía no se enriquecieron.")
    e.add_argument("--tenant", type=UUID, required=True)
    e.add_argument("--busqueda", type=UUID, required=True)
    return p


def _enriquecer(args, ajustes, persistencia, adaptadores) -> int:
    from app.modulos.enriquecimiento.aplicacion.enriquecer_lead import EnriquecerLead

    try:
        if persistencia is None:
            persistencia = _persistencia_postgres(ajustes(), args.tenant)
        verificador, enriquecedor, clasificador = adaptadores(ajustes(), persistencia.costos, cargar_tarifas())
    except ValidationError as error:  # solo los nombres de las variables, nunca sus valores
        print(f"configuración inválida: {', '.join(sorted({str(e['loc'][0]).upper() for e in error.errors()}))}",
              file=sys.stderr)
        return 2
    r = EnriquecerLead(persistencia.repo, verificador, enriquecedor, clasificador).ejecutar(args.busqueda)
    # Solo conteos: el contacto nunca sale de memoria sin cifrar.
    print(f"procesados {r.procesados} · contactables {r.contactables} · clasificados {r.clasificados}"
          f" · sin_clasificar {r.sin_clasificar} · cortado {'sí' if r.cortado else 'no'}")
    return 0


def main(argv=None, *, catalogo=catalogo, persistencia=None, adaptadores=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as salida:
        return int(salida.code or 0)

    @cache
    def ajustes() -> Settings:
        return Settings()

    if args.comando == "enriquecer":
        return _enriquecer(args, ajustes, persistencia, adaptadores or _adaptadores_enriquecer)

    registro = cargar_registro(CONFIG / "fuentes.yaml", catalogo)
    limites = (yaml.safe_load((CONFIG / "fuentes.yaml").read_text()) or {}).get("limites") or {}
    try:
        api_key = None
        if any(meta.proveedor == "croma" for _, meta in registro.fuentes.values()):
            api_key = ajustes().croma_api_key
            if api_key is None:
                print("falta CROMA_API_KEY: hay una fuente de Croma habilitada", file=sys.stderr)
                return 2
        if persistencia is None:
            persistencia = _persistencia_postgres(ajustes(), args.tenant)
    except ValidationError as error:  # solo los nombres de las variables, nunca sus valores
        faltan = sorted({str(e["loc"][0]).upper() for e in error.errors()})
        print(f"configuración inválida: {', '.join(faltan)}", file=sys.stderr)
        return 2

    costos = _ContadorDeCreditos(persistencia.costos)
    tarifas = cargar_tarifas()
    filtros = {k: v for k, v in (("ciiu", args.ciiu), ("departamento", args.departamento), ("ciudad", args.ciudad)) if v}

    def fabrica(clase, meta):
        return armador_de_fuente(clase, meta, ajustes=ajustes, costos=costos, tarifas=tarifas, limites=limites,
                                 api_key=api_key, transporte=httpx.HTTPTransport)

    fuentes = {clave: (meta, fabrica(clase, meta)) for clave, (clase, meta) in registro.fuentes.items()}
    caso = EjecutarBusqueda(persistencia.repo, fuentes, cargar_actividades(CONFIG / "actividades.yaml"))
    resultado = caso.ejecutar(CriteriosICP(args.pais, filtros))

    print(f"encontrados {resultado.encontrados} · únicos {resultado.unicos} · nuevos {resultado.nuevos}"
          f" · créditos {costos.creditos}")
    if resultado.sin_fuente_para:
        print(f"sin_fuente_para: {resultado.sin_fuente_para[0]}")
    for clave, error in sorted(resultado.errores.items()):
        print(f"error en {clave}: {type(error).__name__}")
    print(f"sin_implementacion: {', '.join(sorted(registro.sin_implementacion))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
