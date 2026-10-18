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

from app.composicion import CONFIG, armador_de_fuente, cargar_tarifas
from app.config import Settings, SettingsEmail
from app.modulos.contacto.dominio.errores import MensajeCambio, SinVistaPrevia
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


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="comando", required=True)
    b = sub.add_parser("buscar", help="Busca empresas que cumplen el ICP en las fuentes habilitadas.")
    b.add_argument("--tenant", type=UUID, required=True)
    b.add_argument("--pais", required=True)
    b.add_argument("--ciiu")
    b.add_argument("--departamento")
    b.add_argument("--ciudad")
    e = sub.add_parser("enviar", help="Manda el mensaje base a los contactos aprobados por el --dry-run de la búsqueda.")
    e.add_argument("--tenant", type=UUID, required=True)
    e.add_argument("--busqueda", type=UUID, required=True)
    e.add_argument("--dry-run", action="store_true", help="Aprueba los contactos y muestra el resumen; no manda nada.")
    e.add_argument("--rehacer", action="store_true", help="Con --dry-run: recompone los aprobados si cambió el mensaje.")
    return p


def _invalida(error: ValidationError) -> int:
    """Solo los nombres de las variables, nunca sus valores."""
    faltan = sorted({str(e["loc"][0]).upper() for e in error.errors() if e["loc"]} or {"SETTINGS"})
    print(f"configuración inválida: {', '.join(faltan)}", file=sys.stderr)
    return 2


def _hay_ruta_de_baja() -> bool:
    from app.main import app
    return any(getattr(r, "path", None) == "/baja/{token}" for r in app.routes)


def _armar_envio_postgres(ajustes: SettingsEmail, tenant: UUID):
    # ponytail: sin adaptador de leads contactables hasta que mergee la 006; el CLI corta acá.
    raise NotImplementedError("falta el adaptador de leads contactables (spec 006)")


def _enviar(args, armar_envio) -> int:
    try:
        ajustes = SettingsEmail()
    except ValidationError as error:
        return _invalida(error)
    if ajustes.email_modo == "real" and not _hay_ruta_de_baja():
        print("EMAIL_MODO=real sin /baja/{token} en la api: no se manda a direcciones reales", file=sys.stderr)
        return 2
    try:
        caso = (armar_envio or _armar_envio_postgres)(ajustes, args.tenant)
    except NotImplementedError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        if args.dry_run:
            r = caso.vista_previa(args.busqueda, rehacer=args.rehacer)
            print(f"modo: {r.modo}\naprobados: {r.aprobados}\na enviar: {r.a_enviar}")
            if r.asunto is not None:
                print(f"asunto: {r.asunto}\n\n{r.cuerpo}")
            return 0
        print(f"enviados: {caso.enviar(args.busqueda)}")
        return 0
    except SinVistaPrevia:
        print("sin aprobados: corré antes `enviar --dry-run`", file=sys.stderr)
        return 1
    except MensajeCambio:
        print("el mensaje cambió desde el dry-run: corré `enviar --dry-run --rehacer` y revisá", file=sys.stderr)
        return 1


def main(argv=None, *, catalogo=catalogo, persistencia=None, armar_envio=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as salida:
        return int(salida.code or 0)
    if args.comando == "enviar":
        return _enviar(args, armar_envio)

    @cache
    def ajustes() -> Settings:
        return Settings()

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
    except ValidationError as error:
        return _invalida(error)

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
