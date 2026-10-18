"""Puertos de intake. El consumidor es dueño de su puerto: los adaptadores los cumplen por estructura (Protocol) sin
importar nada de este módulo, y `intake` no importa a sus proveedores. Solo la raíz de composición ve a los dos."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class GeneradorEstructurado(Protocol):
    def generar(self, frase: str, lote_id: UUID) -> dict:
        """Frase -> objeto con la forma del esquema de la sugerencia, tal como lo dio el modelo (sin validar contra los
        catálogos). Escribe sus costos con `lote_id` ANTES de devolver o lanzar. Lanza `SalidaIntakeInvalida` si la
        respuesta no trae el objeto, y `ErrorGeneracion` si el proveedor no respondió."""
        ...


@dataclass(frozen=True)
class ContextoCosto:
    """Dónde se anota el gasto de una consulta: `fuente` y `lote_id` de la corrida (la fila sale con lead_id NULL)."""

    fuente: str
    lote_id: UUID


@runtime_checkable
class CoincidenciaRues(Protocol):
    """Una empresa que el registro mercantil devolvió para un nombre. Atributos de solo lectura."""

    @property
    def nit(self) -> str: ...

    @property
    def ciiu(self) -> str | None: ...

    @property
    def departamento(self) -> str | None: ...

    @property
    def ciudad(self) -> str | None: ...

    @property
    def estado_matricula(self) -> str | None: ...


@runtime_checkable
class BuscadorRazonSocial(Protocol):
    """Puerta A (lookalike). Lo declara intake; lo cumple el adaptador de RUES que el arranque le inyecte."""

    def buscar_coincidencias(self, nombre_normalizado: str, contexto_costo: ContextoCosto) -> list[CoincidenciaRues]:
        """Todas las coincidencias del nombre. El adaptador escribe su costo (con `contexto_costo`) antes de devolver."""
        ...
