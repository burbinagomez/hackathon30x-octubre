from uuid import UUID

TOPE_POR_CORRIDA = 20


class EnviarABusqueda:
    def vista_previa(self, busqueda_id: UUID) -> list[tuple[str, str]]:
        raise NotImplementedError

    def __call__(self, busqueda_id: UUID) -> int:
        raise NotImplementedError
