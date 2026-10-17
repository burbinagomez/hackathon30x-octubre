---
name: libro-costos
description: Cómo toda operación de salida registra su costo en la tabla `costos` y cómo se calculan CPL y CPQL. Cárgala antes de tocar cualquier adaptador que consulte una fuente, llame a un LLM/Jev/Croma, envíe un mensaje o hable con Dapta. Es el diferenciador del proyecto; no se omite.
---

# Libro de costos

## Principio
La fuente es gratis; el lead no. **Cada operación de salida escribe una fila en `costos` en el momento en que ocurre**, antes de devolver su resultado. CPL y CPQL se calculan únicamente desde esa tabla. Nada se estima.

## Puerto
```python
class RegistroCostos(Protocol):
    def registrar(self, op: OperacionCosto) -> None: ...

@dataclass(frozen=True)
class OperacionCosto:
    tipo: TipoOperacion            # ver tabla
    unidades: Decimal              # segundos, tokens, créditos, mensajes, minutos
    costo_unitario: Decimal        # desde config/tarifas.yaml
    moneda: str                    # "USD"
    proveedor: str                 # "datos.gov.co" | "osm" | "croma" | "jev" | "anthropic" | "smtp" | "meta" | "dapta" | "humano"
    fuente: str | None             # fuente de descubrimiento a la que se atribuye
    canal: str | None              # "email" | "whatsapp" | None
    lead_id: UUID | None           # None = costo de lote, se prorratea
    lote_id: UUID | None
    ts: datetime
```
Todo adaptador de salida recibe un `RegistroCostos` por inyección. **Un adaptador que no lo recibe no compila el test de arquitectura.**

## Tipos de operación y unidad
| tipo | unidad | tarifa en `tarifas.yaml` |
|---|---|---|
| `socrata_descarga` | segundos de cómputo | `computo_seg_usd` |
| `overpass_query` | segundos | `computo_seg_usd` |
| `web_fetch` | request | `web_fetch_usd` |
| `llm_tokens_in` / `llm_tokens_out` | tokens | `llm.<modelo>.in_usd_por_M` / `.out_usd_por_M` |
| `jev_tokens` | tokens | `jev.in_usd_por_M` (0.042) |
| `croma_consulta` | créditos (1 dataset / 10 live) | `croma.usd_por_credito` |
| `email_envio` | mensaje | `email.usd_por_mensaje` |
| `whatsapp_plantilla` | mensaje | `whatsapp.usd_por_plantilla_co` |
| `dapta_llamada` | minutos | `dapta.usd_por_minuto` (**[MENTORES]**) |
| `minutos_humanos` | minutos | `humano.usd_por_minuto` |

Tier gratis ≠ costo cero en el libro: se registra el **valor de lista** y se marca `gratis=true`, para que el modelo siga siendo honesto al escalar. El tablero muestra ambas vistas.

## Atribución
- Operación con `lead_id` → al lead, y por tanto a su fuente de descubrimiento y a su canal.
- Operación de lote (`lead_id=None`, `lote_id` set) → se prorratea en partes iguales entre los leads **únicos ICP** que produjo ese lote. Si el lote produjo cero, el costo queda como "desperdicio de fuente" (métrica propia).
- Un lead encontrado por dos fuentes: el costo de cada fuente se atribuye a esa fuente; el lead cuenta como único para ambas en "encontrados" y una sola vez en "únicos".

## Fórmulas
```
CPL(fuente)               = Σ costos(fuente) / leads_unicos_icp(fuente)
costo_por_respuesta(canal)= Σ costos(descubrimiento prorrateado + contacto, canal) / respuestas_reales(canal)
CPQL(fuente, canal)       = Σ costos(descubrimiento + enriquecimiento + contacto + dapta) / demos_agendadas(fuente, canal)
```
Divisor cero → se muestra "sin dato", nunca 0 ni infinito.

## Tests obligatorios
- Por cada tipo de operación: test de integración con proveedor falso que verifica la fila en `costos` con unidades y tarifa correctas.
- Test de arquitectura: todo adaptador en `infraestructura/` que haga I/O externo depende de `RegistroCostos`.
- Test de fórmulas con un fixture de 10 leads, 2 fuentes, 2 canales, costos de lote y por lead, y resultado calculado a mano.

## Tablero
Las consultas del tablero leen vistas SQL sobre `costos` + `leads` + `contactos` + `calificaciones`. Nada se calcula en el front.
