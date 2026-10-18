"""Raíz de composición: único módulo que une descubrimiento con la infraestructura de costos."""
import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from uuid import UUID, uuid4

import httpx
import yaml
from pydantic import ValidationError

from app.composicion import CONFIG, adaptadores_enriquecer, armador_de_fuente, buscador_sitio_web, cargar_tarifas
from app.config import Settings, SettingsEmail
from app.modulos.contacto.dominio.errores import MensajeCambio, SinVistaPrevia
from app.modulos.contacto.dominio.tokens import firmar
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
    e = sub.add_parser("enviar", help="Manda el mensaje base a los contactos aprobados por el --dry-run de la búsqueda.")
    e.add_argument("--tenant", type=UUID, required=True)
    e.add_argument("--busqueda", type=UUID, required=True)
    e.add_argument("--dry-run", action="store_true", help="Aprueba los contactos y muestra el resumen; no manda nada.")
    e.add_argument("--rehacer", action="store_true", help="Con --dry-run: recompone los aprobados si cambió el mensaje.")
    d = sub.add_parser("baja", help="Da de baja a mano (via humano) al lead de un contacto: cierra todos los canales.")
    d.add_argument("--tenant", type=UUID, required=True)
    d.add_argument("--contacto", type=UUID, required=True)
    r = sub.add_parser("respondio", help="Marca a mano que el contacto respondió (solo si se le envió).")
    r.add_argument("--tenant", type=UUID, required=True)
    r.add_argument("--contacto", type=UUID, required=True)
    t = sub.add_parser("tasa-respuesta", help="Contactados, respondieron y tasa por canal del tenant.")
    t.add_argument("--tenant", type=UUID, required=True)
    n = sub.add_parser("enriquecer", help="Enriquece los leads de una búsqueda que todavía no se enriquecieron.")
    n.add_argument("--tenant", type=UUID, required=True)
    n.add_argument("--busqueda", type=UUID, required=True)
    return p


def _contactos(args) -> int:
    """baja, respondio y tasa-respuesta: van directo al repo, sin caso de uso propio."""
    from app import db
    from app.modulos.contacto.infraestructura.repositorio_contactos import RepositorioContactosPostgres

    try:
        settings = Settings()
    except ValidationError as error:
        return _invalida(error)
    repo = RepositorioContactosPostgres(db.crear_engine(settings.database_url), args.tenant)
    if args.comando == "tasa-respuesta":
        filas = repo.tasa_por_canal()
        for canal, contactados, respondieron, tasa in filas:
            print(f"{canal}: contactados={contactados} respondieron={respondieron} "
                  f"tasa={'sin dato' if tasa is None else tasa.normalize()}")
        if not filas:
            print("sin contactos")
        return 0
    if args.comando == "respondio":
        hecho, falta = repo.marcar_respondio(args.contacto), "no hay un envío de ese contacto en ese tenant"
    else:
        hecho, falta = repo.dar_de_baja(args.contacto, "humano"), "no existe ese contacto en ese tenant"
    if not hecho:
        print(falta, file=sys.stderr)
        return 1
    print(f"{args.comando}: 1")
    return 0


def _invalida(error: ValidationError) -> int:
    """Solo los nombres de las variables, nunca sus valores."""
    faltan = sorted({str(e["loc"][0]).upper() for e in error.errors() if e["loc"]} or {"SETTINGS"})
    print(f"configuración inválida: {', '.join(faltan)}", file=sys.stderr)
    return 2


def _hay_ruta_de_baja(ajustes: SettingsEmail, tenant: UUID, transporte: httpx.BaseTransport | None = None) -> bool:
    """La API desplegada en API_BASE_URL acepta un token firmado con esta BAJA_SECRET: los enlaces que mandamos andan."""
    token = firmar(ajustes.baja_secret.get_secret_value().encode(), "baja", tenant, uuid4())
    try:
        with httpx.Client(transport=transporte, timeout=5) as cliente:
            return cliente.get(f"{ajustes.api_base_url.rstrip('/')}/baja/{token}").status_code == 200
    except httpx.HTTPError:
        return False


def _armar_envio_postgres(ajustes: SettingsEmail, tenant: UUID):
    from app import db
    from app.modulos.contacto.aplicacion.envio import EnviarABusqueda
    from app.modulos.contacto.infraestructura.leads_contactables import LeadsContactablesPostgres
    from app.modulos.contacto.infraestructura.repositorio_contactos import RepositorioContactosPostgres
    from app.modulos.contacto.infraestructura.smtp_email import SmtpEmail
    from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
    from app.seguridad.cifrado import Cifrador

    engine = db.crear_engine(ajustes.database_url)
    tarifa = Decimal(str(yaml.safe_load((CONFIG / "tarifas.yaml").read_text())["email"]["usd_por_mensaje"]))
    return EnviarABusqueda(
        tenant, RepositorioContactosPostgres(engine, tenant),
        LeadsContactablesPostgres(engine, tenant, Cifrador(ajustes.cifrado_key.get_secret_value())),
        SmtpEmail(ajustes, PostgresCostos(engine, tenant), tarifa),
        clave_baja=ajustes.baja_secret.get_secret_value().encode(), remitente=ajustes.remitente,
        url_api=ajustes.api_base_url, url_privacidad=ajustes.url_privacidad, modo=ajustes.email_modo,
        destinos_prueba=ajustes.email_prueba_destinos)


def _enviar(args, armar_envio) -> int:
    try:
        ajustes = SettingsEmail()
    except ValidationError as error:
        return _invalida(error)
    if ajustes.email_modo == "real" and not _hay_ruta_de_baja(ajustes, args.tenant):
        print("EMAIL_MODO=real y /baja/{token} no responde en API_BASE_URL con esta BAJA_SECRET: no se manda", file=sys.stderr)
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
    # El buscador de sitio web solo con los adaptadores reales: los tests de la CLI inyectan los suyos.
    buscador = buscador_sitio_web(persistencia.costos, cargar_tarifas(), httpx.HTTPTransport()) \
        if adaptadores is _adaptadores_enriquecer else None
    r = EnriquecerLead(persistencia.repo, verificador, enriquecedor, clasificador, buscador=buscador).ejecutar(args.busqueda)
    # Solo conteos: el contacto nunca sale de memoria sin cifrar.
    print(f"procesados {r.procesados} · contactables {r.contactables} · clasificados {r.clasificados}"
          f" · sin_clasificar {r.sin_clasificar} · cortado {'sí' if r.cortado else 'no'}")
    return 0


def main(argv=None, *, catalogo=catalogo, persistencia=None, adaptadores=None, armar_envio=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as salida:
        return int(salida.code or 0)
    if args.comando == "enviar":
        return _enviar(args, armar_envio)
    if args.comando in ("baja", "respondio", "tasa-respuesta"):
        return _contactos(args)

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
