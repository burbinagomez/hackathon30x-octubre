"""Exportación de candidatos (T020): whitelist del dataset aplicada sobre leads de un repositorio falso (D4).

Datos sintéticos: el contacto usa dominio .invalid y numeración ficticia; está acá para probar que NO sale.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.modulos.descubrimiento.dominio.modelos import Lead
from evals import esquema
from evals.exportar_candidatos import Origen, main

RAIZ = Path(__file__).resolve().parents[4]
CROMA = sorted(esquema.FUENTES_CROMA)[0]
AS_OF = datetime(2026, 10, 1, tzinfo=UTC)

NIT = "900123456"
WEB = "https://ferreteria-sintetica.invalid"
EMAIL = "compras@ferreteria-sintetica.invalid"
TELEFONO = "+57 604 555 0101"
INGRESOS = 12_000_000_000  # COP: bucket "mediana"


@dataclass(frozen=True)
class LeadConContacto(Lead):
    """Un Lead que además trae contacto: la exportación tiene que elegir campos, no confiar en lo que llega."""
    email: str | None = None
    telefono: str | None = None


def _lead(**kw) -> LeadConContacto:
    base = dict(id=uuid4(), pais="CO", tipo_titular="juridica", nombre="Ferreteria Sintetica SAS",
                direccion="Calle Sintetica 1", id_fiscal=NIT, ciudad="Medellin", web=WEB, email=EMAIL, telefono=TELEFONO)
    return LeadConContacto(**(base | kw))


class RepoLeadsFalso:
    """Forma de RepositorioLeads del 002: la exportación solo lee con obtener_lead."""

    def __init__(self, leads):
        self._leads = {lead.id: lead for lead in leads}

    def obtener_lead(self, lead_id: UUID) -> Lead | None:
        return self._leads.get(lead_id)


CROMA_LEAD = _lead()
OSM_JURIDICA = _lead(nombre="Ferreteria La Esquina Sintetica", id_fiscal=None, ciudad="Bogota")
OSM_DESCONOCIDO = _lead(tipo_titular="desconocido", nombre="Tienda Don Sintetico", id_fiscal=None)
REPO = RepoLeadsFalso([CROMA_LEAD, OSM_JURIDICA, OSM_DESCONOCIDO])
BUSQUEDA = uuid4()
ORIGENES = {BUSQUEDA: [
    # Fuente fuera de esquema.FUENTES, antes de la OSM del mismo lead: sin el filtro, ganaría ella.
    Origen(OSM_JURIDICA.id, "datos_gov_co_rues", AS_OF, "CC-BY-SA-4.0"),
    # El lead de Croma también vino de OSM, y primero: Croma tiene que ganar igual (sin nombre).
    Origen(CROMA_LEAD.id, esquema.OSM, AS_OF, "ODbL-1.0"),
    Origen(CROMA_LEAD.id, CROMA, AS_OF, "terminos-croma", actividad="4752", ingresos_cop=INGRESOS),
    Origen(OSM_JURIDICA.id, esquema.OSM, AS_OF, "ODbL-1.0", actividad="4752"),
    Origen(OSM_DESCONOCIDO.id, esquema.OSM, AS_OF, "ODbL-1.0"),
]}


def _exportar(tmp_path: Path, nombre: str) -> tuple[int, str]:
    salida = tmp_path / nombre
    codigo = main(["--tenant", str(uuid4()), "--busqueda", str(BUSQUEDA)], repo=REPO, listar=ORIGENES.__getitem__,
                  salida=salida)
    return codigo, salida.read_text()


def _por_fuente(casos):
    croma = [c for c in casos if c.get("origen", {}).get("fuente") == CROMA]
    osm = [c for c in casos if c.get("origen", {}).get("fuente") == esquema.OSM]
    return croma, osm


def test_aplica_whitelist(tmp_path):
    codigo, texto = _exportar(tmp_path, "uno.json")
    _, texto_2 = _exportar(tmp_path, "dos.json")
    casos = json.loads(texto)["casos"]
    croma, osm = _por_fuente(casos)

    assert codigo == 0 and len(casos) == 3  # un caso por lead, aunque tenga varias fuentes
    assert {c["origen"]["fuente"] for c in casos} <= esquema.FUENTES
    # CROMA_LEAD sale como Croma y sin nombre, aunque su origen OSM llegó primero.
    assert len(croma) == 1 and all(c.get("nombre") != CROMA_LEAD.nombre for c in casos)
    for prohibido in (NIT, WEB, EMAIL, TELEFONO, str(INGRESOS), CROMA_LEAD.nombre, CROMA_LEAD.direccion):
        assert prohibido not in texto
    assert esquema.problemas_contacto("dataset.json", json.loads(texto)) == []
    assert all(c["etiqueta"] is None for c in casos)

    [caso_croma] = croma
    assert "nombre" not in caso_croma and "tipo_titular" not in caso_croma
    assert caso_croma.keys() <= {"id", "pais", "actividad", "departamento", "ciudad", "rango_ingresos", "origen", "etiqueta"}
    assert caso_croma["rango_ingresos"] == "mediana"
    assert re.fullmatch(r"c-[0-9a-f]{12}", caso_croma["id"])
    assert caso_croma["id"][2:] != hashlib.sha256(f"CO:{NIT}".encode()).hexdigest()[:12]
    [caso_croma_2] = _por_fuente(json.loads(texto_2)["casos"])[0]
    assert caso_croma_2["id"] != caso_croma["id"]  # al azar en cada exportación: el id no sale del NIT

    juridica = [c for c in osm if c["tipo_titular"] == "juridica"]
    desconocido = [c for c in osm if c["tipo_titular"] == "desconocido"]
    assert [c.get("nombre") for c in juridica] == [OSM_JURIDICA.nombre]
    assert [("nombre" in c) for c in desconocido] == [False]
    assert all(re.fullmatch(r"o-[0-9a-f]{12}", c["id"]) for c in osm)
    assert esquema.problemas_dataset({"icp": {}, "casos": [c | {"etiqueta": "encaja"} for c in casos]}) \
        == ["icp:$.icp", "n_casos:$.casos", "min_por_etiqueta:encaja", "min_por_etiqueta:no_encaja"]  # solo lo del humano


def test_candidatos_estan_gitignored():
    assert "backend/evals/dataset.candidatos.json" in (RAIZ / ".gitignore").read_text().splitlines()
