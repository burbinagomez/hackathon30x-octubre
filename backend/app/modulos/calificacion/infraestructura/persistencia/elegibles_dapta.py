"""Elegibles para llamada de Dapta (spec 008, paso 1): jurídica, con teléfono publicado y sin baja.

El teléfono se descifra solo acá y solo para armar el export (transferencia a un encargado, cumplimiento-datos regla 2).
"""
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db import unidad_de_trabajo
from app.seguridad.cifrado import Cifrador

# Orden de restricción de licencias: la más restrictiva presente es la que viaja con el lead.
_RESTRICCION = {"ODbL": 3, "CC BY-SA 4.0": 2}

_SQL = text("""
    SELECT l.id, l.nombre, l.ciudad, l.telefono_cifrado,
           string_agg(DISTINCT lf.fuente, '; ' ORDER BY lf.fuente) AS fuentes,
           array_agg(DISTINCT lf.licencia) AS licencias
    FROM leads l
    JOIN cumplimiento c ON c.tenant_id = l.tenant_id AND c.lead_id = l.id
    LEFT JOIN lead_fuentes lf ON lf.tenant_id = l.tenant_id AND lf.lead_id = l.id
    WHERE l.tipo_titular = 'juridica' AND l.telefono_cifrado IS NOT NULL AND l.telefono_canal IS NOT NULL
      AND c.opt_out_at IS NULL
    GROUP BY l.id, l.nombre, l.ciudad, l.telefono_cifrado
    ORDER BY l.nombre
""")


@dataclass(frozen=True)
class Elegible:
    lead_id: UUID
    empresa: str
    telefono: str
    ciudad: str | None
    fuentes: str
    licencia: str


def elegibles_dapta(engine: Engine, tenant_id: UUID, cifrador: Cifrador) -> Iterator[Elegible]:
    with unidad_de_trabajo(engine, tenant_id) as c:
        filas = c.execute(_SQL).all()
    for f in filas:
        licencias = [x for x in (f.licencias or []) if x]
        yield Elegible(
            lead_id=f.id, empresa=f.nombre, ciudad=f.ciudad, fuentes=f.fuentes or "",
            telefono=cifrador.descifrar("telefono_cifrado", bytes(f.telefono_cifrado), tenant_id, f.id),
            licencia=max(licencias, key=lambda x: _RESTRICCION.get(x, 1), default=""),
        )
