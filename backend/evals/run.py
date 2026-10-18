"""Runner de evals: `uv run python -m evals.run --tenant <id> [--eval <nombre>] [--actualizar-baseline]`."""
import os


def main(argv, entorno=os.environ, fabrica_juez=None, registro_costos=None) -> int:
    # Stub (T009): 99 no lo espera ningún test; con 0, los tests de baseline de T010 nacerían verdes. Flujo real: T012.
    return 99


# El CI corre este módulo y espera 0: hasta la composición real (T019) no llama a main.
if __name__ == "__main__":
    raise SystemExit(0)
