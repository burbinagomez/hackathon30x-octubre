"""`Sugerencia`: la forma que las dos puertas de intake devuelven = el body de PedidoVistaPrevia (sin canal ni tope).

Departamento y ciudad son lo que la API de vista previa acepta (código nativo de la división, nombre del municipio),
nunca texto libre; CIIU solo si está en el catálogo. Lo que no resuelve sale `None`: el usuario lo completa a mano.
Dominio puro: los catálogos llegan por parámetro.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.modulos.intake.dominio.errores import SalidaIntakeInvalida

PAISES = ("CO", "MX", "PE", "BR")
MAX_PALABRAS = 10  # los mismos límites que PedidoVistaPrevia: la sugerencia tiene que pasar su validación
MAX_LARGO_PALABRA = 40
_CIIU = re.compile(r"\d{4}")


@dataclass(frozen=True)
class Sugerencia:
    pais: str
    ciiu: str | None = None
    departamento: str | None = None
    ciudad: str | None = None
    ingresos_min: int | None = None
    palabras_clave: tuple[str, ...] = ()
    exclusiones: tuple[str, ...] = ()

    def como_dict(self) -> dict:
        return {"pais": self.pais, "ciiu": self.ciiu, "departamento": self.departamento, "ciudad": self.ciudad,
                "ingresos_min": self.ingresos_min, "palabras_clave": list(self.palabras_clave),
                "exclusiones": list(self.exclusiones)}


def _clave(texto: str) -> str:
    """Sin tildes, minúsculas, solo letras y dígitos separados por un espacio."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).split())


def _claves(nombre: str) -> set[str]:
    # "Bogotá, D.C." también se dice "Bogotá": se indexa el nombre entero y lo que va antes de la primera coma.
    return {_clave(nombre), _clave(nombre.split(",")[0])} - {""}


def _texto_o_none(valor: Any) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise SalidaIntakeInvalida("forma_texto")
    return valor.strip() or None


def _division(pais: dict, dicho: str) -> dict | None:
    buscado = _clave(dicho)
    for d in pais["divisiones"]:
        if buscado in {_clave(str(d["codigo_nativo"])), _clave(d.get("iso_3166_2", ""))} \
                | _claves(d.get("nombre_es", "")) | _claves(d.get("nombre_en", "")):
            return d
    return None


def _municipio(division: dict, dicho: str) -> str | None:
    buscado = _clave(dicho)
    return next((m["nombre"] for m in division["municipios"] if buscado in _claves(m["nombre"])), None)


def _ubicacion(pais: dict | None, departamento: str | None, ciudad: str | None) -> tuple[str | None, str | None]:
    if pais is None:
        return None, None
    division = _division(pais, departamento) if departamento else None
    if division is not None:
        return str(division["codigo_nativo"]), (_municipio(division, ciudad) if ciudad else None)
    if not ciudad:
        return None, None
    # Sin departamento (o uno que no existe): la ciudad solo vale si es única en el país; no se adivina entre homónimas.
    halladas = [(d, m) for d in pais["divisiones"] if (m := _municipio(d, ciudad))]
    if len(halladas) != 1:
        return None, None
    return str(halladas[0][0]["codigo_nativo"]), halladas[0][1]


def _ciiu(valor: Any, actividades: dict) -> str | None:
    if isinstance(valor, int) and not isinstance(valor, bool):
        valor = str(valor)
    if not isinstance(valor, str) or not _CIIU.fullmatch(valor.strip()):
        return None
    codigo = valor.strip()
    return codigo if codigo in {str(k) for k in actividades} else None


def _ingresos(valor: Any) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int | float) or valor < 0:
        raise SalidaIntakeInvalida("forma_ingresos_min")
    return int(valor)


def _palabras(valor: Any, campo: str) -> tuple[str, ...]:
    if valor is None:
        return ()
    if not isinstance(valor, list) or not all(isinstance(p, str) for p in valor):
        raise SalidaIntakeInvalida(f"forma_{campo}")
    limpias: list[str] = []
    for p in (p.strip() for p in valor):
        if p and len(p) <= MAX_LARGO_PALABRA and p not in limpias:
            limpias.append(p)
    return tuple(limpias[:MAX_PALABRAS])


def validar_sugerencia(crudo: Any, geografia: dict, actividades: dict) -> Sugerencia:
    """Salida cruda -> `Sugerencia`. Forma rota (no objeto, país fuera del enum, tipos) -> `SalidaIntakeInvalida`
    (se reintenta); catálogo (departamento, ciudad, CIIU que no existen) -> null, sin error."""
    if not isinstance(crudo, dict):
        raise SalidaIntakeInvalida("no_objeto")
    pais = crudo.get("pais")
    if pais not in PAISES:
        raise SalidaIntakeInvalida("forma_pais")
    departamento, ciudad = _ubicacion(geografia.get(pais), _texto_o_none(crudo.get("departamento")),
                                      _texto_o_none(crudo.get("ciudad")))
    return Sugerencia(
        pais=pais, ciiu=_ciiu(crudo.get("ciiu"), actividades), departamento=departamento, ciudad=ciudad,
        ingresos_min=_ingresos(crudo.get("ingresos_min")),
        palabras_clave=_palabras(crudo.get("palabras_clave"), "palabras_clave"),
        exclusiones=_palabras(crudo.get("exclusiones"), "exclusiones"))
