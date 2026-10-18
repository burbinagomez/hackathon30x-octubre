"""Exporta los leads de una búsqueda a dataset.candidatos.json (gitignored) para etiquetarlos a mano (T024).

Whitelist, no blacklist: cada caso se arma con campos elegidos, nunca copiando el lead. Croma sin nombre, sin NIT
y sin tipo_titular, con id al azar; OSM con nombre solo si es jurídica. Fuentes fuera de esquema.FUENTES no salen.

    uv run python -m evals.exportar_candidatos --tenant <uuid> --busqueda <uuid>
"""
import argparse
import json
import secrets
import sys
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from app.modulos.descubrimiento.dominio.modelos import Lead
from app.modulos.descubrimiento.dominio.puertos import RepositorioLeads
from evals import esquema

SALIDA = Path(__file__).resolve().parent / "dataset.candidatos.json"


class Origen(NamedTuple):
    """Una fila de lead_fuentes de la búsqueda, con los rasgos del lead que el Lead del 002 no trae."""
    lead_id: UUID
    fuente: str
    as_of: datetime
    licencia: str
    actividad: str | None = None
    ingresos_cop: int | None = None


def _caso(lead: Lead, o: Origen) -> dict:
    croma = o.fuente in esquema.FUENTES_CROMA
    caso = {"id": ("c-" if croma else "o-") + secrets.token_hex(6), "pais": lead.pais, "ciudad": lead.ciudad,
            "actividad": o.actividad}
    if o.ingresos_cop is not None:
        caso["rango_ingresos"] = esquema.rango_ingresos(o.ingresos_cop)  # el bucket, nunca la cifra
    if not croma:
        caso["tipo_titular"] = lead.tipo_titular
        if lead.tipo_titular == "juridica" and lead.nombre:
            caso["nombre"] = lead.nombre
    caso = {k: v for k, v in caso.items() if v is not None}
    return caso | {"origen": {"fuente": o.fuente, "as_of": o.as_of.isoformat(), "licencia": o.licencia}, "etiqueta": None}


def candidatos(origenes: Iterable[Origen], repo: RepositorioLeads) -> list[dict]:
    # Un caso por lead; si alguna fuente es Croma, manda Croma (la regla más estricta: sin nombre).
    elegido: dict[UUID, Origen] = {}
    for o in origenes:
        if o.fuente in esquema.FUENTES and (o.lead_id not in elegido or o.fuente in esquema.FUENTES_CROMA):
            elegido[o.lead_id] = o
    return [_caso(lead, o) for o in elegido.values() if (lead := repo.obtener_lead(o.lead_id)) is not None]


def _postgres(tenant: UUID) -> tuple[RepositorioLeads, Callable[[UUID], list[Origen]]]:
    from sqlalchemy import text

    from app import db
    from app.config import Settings
    from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres
    from app.seguridad.cifrado import Cifrador

    ajustes = Settings()
    engine = db.crear_engine(ajustes.database_url)

    def listar(busqueda: UUID) -> list[Origen]:
        # Solo lead_fuentes: la tabla leads se lee únicamente por el repositorio (test_cifrado). ponytail: el Lead del
        # 002 no trae actividad ni ingresos, así que salen sin actividad ni rango_ingresos; sumarlos a Lead/obtener_lead.
        with db.unidad_de_trabajo(engine, tenant) as c:
            filas = c.execute(text("SELECT lead_id, fuente, encontrado_en, licencia FROM lead_fuentes "
                                   "WHERE busqueda_id = :b ORDER BY encontrado_en"), {"b": busqueda}).all()
        return [Origen(*f) for f in filas]

    return RepositorioLeadsPostgres(engine, tenant, Cifrador(ajustes.cifrado_key.get_secret_value())), listar


def main(argv=None, *, repo: RepositorioLeads | None = None, listar: Callable[[UUID], Iterable[Origen]] | None = None,
         salida: Path = SALIDA) -> int:
    p = argparse.ArgumentParser(prog="evals.exportar_candidatos")
    p.add_argument("--tenant", type=UUID, required=True)
    p.add_argument("--busqueda", type=UUID, required=True)
    try:
        args = p.parse_args(argv)
    except SystemExit as salida_argparse:
        return int(salida_argparse.code or 0)
    if repo is None or listar is None:
        from pydantic import ValidationError
        try:
            repo, listar = _postgres(args.tenant)
        except ValidationError as error:  # solo los nombres de las variables, nunca sus valores
            print(f"configuración inválida: {', '.join(sorted({str(e['loc'][0]).upper() for e in error.errors()}))}",
                  file=sys.stderr)
            return 2
    casos = candidatos(listar(args.busqueda), repo)
    salida.write_text(json.dumps({"casos": casos}, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(casos)} candidatos en {salida.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
