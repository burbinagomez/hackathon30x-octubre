"""Puertos de la Puerta A. El consumidor es dueño de su puerto: los adaptadores lo cumplen por estructura, sin importar intake."""
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.modulos.costos.dominio.modelos import ContextoCosto


@runtime_checkable
class CoincidenciaRues(Protocol):
    @property
    def nit(self) -> str: ...
    @property
    def ciiu(self) -> str | None: ...
    @property
    def camara(self) -> str | None: ...
    @property
    def estado_matricula(self) -> str | None: ...


@runtime_checkable
class BuscadorRazonSocial(Protocol):
    def buscar_coincidencias(
        self, nombre_normalizado: str, contexto_costo: ContextoCosto
    ) -> Sequence[CoincidenciaRues]: ...
