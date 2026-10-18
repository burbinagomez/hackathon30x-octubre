"""EnriquecerLead + BuscadorSitioWeb: cuándo se busca, qué se guarda, y la tanda en paralelo con presupuesto de tiempo.
Repo, buscador y enriquecedor falsos en memoria; sin red ni base."""
import threading
from uuid import uuid4

from app.modulos.descubrimiento.dominio.modelos import EvidenciaSitioWeb, LeadParaEnriquecer
from app.modulos.enriquecimiento.aplicacion.enriquecer_lead import EnriquecerLead
from app.modulos.enriquecimiento.dominio.puertos import ContactoPublicado, VerificacionTitular

TEL = ("573005550101", "sitio_web")


def _lead(tipo="juridica", web=None, nombre="Grupo Processa SAS", nit="900123456", **kw) -> LeadParaEnriquecer:
    return LeadParaEnriquecer(id=uuid4(), tipo_titular=tipo, nombre=nombre, ciudad="Cali", web=web, actividad="5229",
                              descripcion_icp=None, pais="CO", id_fiscal=nit, **kw)


class Repo:
    def __init__(self, leads):
        self.leads, self.guardados = leads, {}

    def sin_enriquecer(self, busqueda_id):
        return [lead for lead in self.leads if lead.id not in self.guardados]

    def guardar_enriquecimiento(self, lead_id, r):
        self.guardados[lead_id] = r


class Buscador:
    def __init__(self, hallazgo="grupoprocessa.com.co", motivo="nit"):
        self.llamadas, self.hallazgo, self.motivo = [], hallazgo, motivo

    def buscar(self, lead_id, razon_social, nit):
        self.llamadas.append((lead_id, razon_social, nit))
        return None if self.hallazgo is None else EvidenciaSitioWeb(self.hallazgo, f"https://{self.hallazgo}/", self.motivo)


class Sitio:
    def __init__(self, contacto=None):
        self.dominios = []
        self.contacto = contacto or ContactoPublicado((), (TEL,), "ok")

    def enriquecer(self, lead_id, dominio):
        self.dominios.append(dominio)
        return self.contacto


class Verificador:
    def verificar(self, lead_id, nombre, ciudad, pais):
        return VerificacionTitular("juridica", "match_unico")


def _caso(leads, buscador, sitio=None, **kw):
    repo, sitio = Repo(leads), sitio or Sitio()
    return EnriquecerLead(repo, Verificador(), sitio, None, buscador=buscador, **kw), repo, sitio


def test_juridica_sin_web_se_busca_y_con_la_web_hallada_sigue_sitio_web():
    lead = _lead()
    buscador = Buscador()
    caso, repo, sitio = _caso([lead], buscador)

    caso.ejecutar(uuid4())

    assert buscador.llamadas == [(lead.id, "Grupo Processa SAS", "900123456")]
    assert sitio.dominios == ["grupoprocessa.com.co"]
    r = repo.guardados[lead.id]
    assert (r.web, r.telefono, r.contactable) == ("grupoprocessa.com.co", TEL, True)
    assert r.evidencia_web == EvidenciaSitioWeb("grupoprocessa.com.co", "https://grupoprocessa.com.co/", "nit")


def test_si_no_encuentra_no_guarda_web_ni_llama_a_sitio_web():
    lead = _lead()
    caso, repo, sitio = _caso([lead], Buscador(hallazgo=None))

    caso.ejecutar(uuid4())

    r = repo.guardados[lead.id]
    assert (r.web, r.evidencia_web, r.contactable, r.razon_no_contactable) == (None, None, False, "sin_canal_publicado")
    assert sitio.dominios == []


def test_juridica_con_web_no_se_busca():
    lead = _lead(web="andinos.invalid")
    buscador = Buscador()
    caso, repo, sitio = _caso([lead], buscador)

    caso.ejecutar(uuid4())

    assert buscador.llamadas == [] and sitio.dominios == ["andinos.invalid"]
    assert repo.guardados[lead.id].web is None  # ya la tenía: no se reescribe


def test_natural_no_se_busca():
    buscador = Buscador()
    caso, repo, sitio = _caso([_lead(tipo="natural")], buscador)

    caso.ejecutar(uuid4())

    assert buscador.llamadas == [] and sitio.dominios == []


def test_desconocido_se_busca_solo_si_el_verificador_lo_sube_a_juridica():
    class NoMatch(Verificador):
        def verificar(self, *a):
            return VerificacionTitular("desconocido", "sin_match")
    buscador = Buscador()
    repo = Repo([_lead(tipo="desconocido")])
    EnriquecerLead(repo, NoMatch(), Sitio(), None, buscador=buscador).ejecutar(uuid4())
    assert buscador.llamadas == []

    caso, _, _ = _caso([_lead(tipo="desconocido")], buscador)
    caso.ejecutar(uuid4())
    assert len(buscador.llamadas) == 1


def test_sin_buscador_configurado_todo_sigue_como_antes():
    lead = _lead()
    caso, repo, sitio = _caso([lead], None)

    caso.ejecutar(uuid4())

    assert sitio.dominios == [] and repo.guardados[lead.id].web is None


def test_lead_sin_nit_se_busca_solo_por_razon_social():
    lead = _lead(nit=None)
    buscador = Buscador(motivo="razon_social")
    caso, _, _ = _caso([lead], buscador)

    caso.ejecutar(uuid4())

    assert buscador.llamadas == [(lead.id, "Grupo Processa SAS", None)]


# --- tanda en paralelo con presupuesto de tiempo ------------------------------------------------------------------

class Concurrente(Sitio):
    """Cuenta cuántos leads están dentro a la vez y los retiene hasta que llegan 8 (o 5 s)."""

    def __init__(self):
        super().__init__()
        self._candado, self.activos, self.maximo = threading.Lock(), 0, 0
        self.ocho = threading.Event()

    def enriquecer(self, lead_id, dominio):
        with self._candado:
            self.activos += 1
            self.maximo = max(self.maximo, self.activos)
            if self.activos == 8:
                self.ocho.set()
        self.ocho.wait(5)
        with self._candado:
            self.activos -= 1
        return self.contacto


def test_la_tanda_corre_en_paralelo_con_ocho_hilos_como_maximo():
    sitio = Concurrente()
    leads = [_lead(web=f"a{i}.invalid") for i in range(12)]
    caso, repo, _ = _caso(leads, None, sitio, max_hilos=8)

    r = caso.ejecutar(uuid4())

    assert sitio.maximo == 8
    assert (r.procesados, r.pendientes) == (12, 0) and len(repo.guardados) == 12


def test_el_presupuesto_agotado_deja_pendientes_a_los_que_no_terminaron():
    soltar = threading.Event()

    class Lento(Sitio):
        def enriquecer(self, lead_id, dominio):
            if dominio == "lento.invalid":
                soltar.wait(10)
            return self.contacto
    rapidos = [_lead(web=f"r{i}.invalid") for i in range(3)]
    lento = _lead(web="lento.invalid")
    caso, repo, _ = _caso([*rapidos, lento], None, Lento(), max_hilos=8)

    try:
        r = caso.ejecutar(uuid4(), presupuesto_s=0.3)
    finally:
        soltar.set()

    assert (r.procesados, r.pendientes, r.cortado) == (3, 1, False)
    assert set(repo.guardados) == {x.id for x in rapidos} and lento.id not in repo.guardados


def test_con_el_presupuesto_ya_vencido_no_arranca_ningun_lead():
    tiempo = iter([0.0])
    reloj = lambda: next(tiempo, 100.0)  # noqa: E731  la primera lectura es el inicio; después ya pasaron 100 s
    sitio = Sitio()
    caso, repo, _ = _caso([_lead(web=f"x{i}.invalid") for i in range(4)], None, sitio, max_hilos=2, reloj=reloj)

    r = caso.ejecutar(uuid4(), presupuesto_s=60.0)

    assert (r.procesados, r.pendientes) == (0, 4)
    assert sitio.dominios == [] and repo.guardados == {}


def test_sin_presupuesto_no_hay_corte():
    leads = [_lead(web=f"x{i}.invalid") for i in range(5)]
    caso, repo, _ = _caso(leads, None, max_hilos=2)

    r = caso.ejecutar(uuid4())

    assert (r.procesados, r.pendientes) == (5, 0)
