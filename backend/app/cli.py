"""Raíz de composición: único módulo que une descubrimiento con la infraestructura de costos."""
from dataclasses import dataclass

from app.modulos.costos.dominio.puertos import RegistroCostos
from app.modulos.descubrimiento.dominio.puertos import RepositorioLeads
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo


@dataclass(frozen=True)
class Persistencia:
    repo: RepositorioLeads
    costos: RegistroCostos


def main(argv=None, *, catalogo=catalogo, persistencia=None) -> int:
    return 0
