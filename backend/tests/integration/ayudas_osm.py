"""EjecutarBusqueda real con OSM falso: lo comparten los tests de integración que corren una búsqueda."""
import json
from decimal import Decimal
from pathlib import Path

import httpx

from app.modulos.costos.infraestructura.postgres_costos import PostgresCostos
from app.modulos.descubrimiento.aplicacion.ejecutar_busqueda import EjecutarBusqueda
from app.modulos.descubrimiento.aplicacion.registro import cargar_actividades, cargar_registro
from app.modulos.descubrimiento.dominio.modelos import CriteriosICP
from app.modulos.descubrimiento.infraestructura.adaptadores import catalogo
from app.modulos.descubrimiento.infraestructura.persistencia.repositorio_leads import RepositorioLeadsPostgres

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((BACKEND / "tests" / "fixtures" / "osm" / "bogota_4711.json").read_text())
TARIFA = Decimal("0.0000070")
ICP = CriteriosICP("CO", {"ciiu": "4711", "ciudad": "Bogotá"})


def buscar_osm(rt, tenant, cifrador):
    """Catálogo real, OSM con transporte falso (2 s por request) y Postgres real."""
    registro = cargar_registro(BACKEND / "config" / "fuentes.yaml", catalogo)
    clase, meta = registro.fuentes["osm_overpass"]
    ahora = [0.0]

    def responder(request):
        ahora[0] += 2.0
        return httpx.Response(200, json=FIXTURE)

    def fabrica(lote_id):
        return clase(meta=meta, registro_costos=PostgresCostos(rt, tenant), transporte=httpx.MockTransport(responder),
                     costo_unitario=TARIFA, lote_id=lote_id, repo_url="https://example.invalid/repo",
                     reloj=lambda: ahora[0])

    caso = EjecutarBusqueda(RepositorioLeadsPostgres(rt, tenant, cifrador), {"osm_overpass": (meta, fabrica)},
                            actividades=cargar_actividades(BACKEND / "config" / "actividades.yaml"))
    return caso.ejecutar(ICP)
