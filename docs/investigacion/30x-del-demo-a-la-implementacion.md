# 30X Hackathon — "Del demo a la implementación"
### Charla de Sandra Carrillo · Workshops de preparación (12–15 oct)

> Pistas de lo que los jueces buscan. El hilo conductor: **lo que separa un demo de un piloto que la empresa puede aprobar.** No necesitas todo resuelto, pero sí mostrar que pensaste en cada frente.

El reto de ejemplo que usó: **Clínicas Sanamar** (empresa ficticia) — red de 14 sedes, problema de pacientes que no llegan a sus citas. 8.800 citas perdidas al mes, ~$290M COP que la clínica deja de facturar.

---

## Las 5 etapas del recorrido

| # | Etapa | Herramientas sugeridas |
|---|-------|------------------------|
| 01 | Entender el reto | NotebookLM, Claude, Perplexity, Codex |
| 02 | Recortar y construir | Claude, Lovable, Claude Code, Supabase |
| 03 | Hacerlo implementable | Seguridad, tests, CI, costos |
| 04 | Un demo que no se rompa | Vercel, datos de prueba, Cap |
| 05 | El pitch para quien decide | Gamma, Claude, README |

---

## Etapa 01 — Entender el reto

La clave está en **preguntar bien**. Las preguntas que hizo Sandra para destapar el problema real:

- "¿Qué le duele más a esta empresa?"
- "¿Dónde se concentra el problema?"
- "¿Qué métrica importa más en esta área?"
- "¿Qué métrica no están nombrando y deberían tener en cuenta?"

Lo que apareció al preguntar así:
1. **El problema está concentrado** — no es "todas las citas", son las primeras citas con especialista, agendadas con +15 días, de pacientes que viven lejos.
2. **Cancelar no libera el cupo** — la lista de espera vive en un Excel por sede y nadie alcanza a reasignar a tiempo.
3. **La métrica real es la ocupación** — el brief habla de inasistencia, pero quien decide responde por la agenda ocupada. (Habla en el idioma de quien aprueba el proyecto.)

---

## Etapa 02 — Recortar el alcance y construir rápido

> "Un flujo completo que funcione el domingo vale más que cinco funcionalidades a medias."

Tres piezas:
- **PRD** — una página con el usuario, el flujo principal y, sobre todo, lo que queda fuera. *(Claude o Codex)*
- **Construye** — del PRD a un prototipo funcional. Si prefieres tu editor y tu propio código, Claude Code hace lo mismo. *(Lovable o Claude Code)*
- **Backend e infraestructura** — base de datos, autenticación y despliegue resueltos, para no gastar el sábado configurando servidores. *(Supabase y Vercel)*

**Ejemplo de mini PRD (Sanamar):**
- *Para quién:* coordinadores de sede y pacientes de primeras citas con especialista.
- *Flujo principal:* (1) un panel marca las citas con alto riesgo de inasistencia → (2) el paciente confirma o cancela por WhatsApp → (3) si cancela, el cupo se ofrece a la lista de espera.
- *Fuera del alcance:* integración directa con el software clínico (usan CSV), app móvil, pagos.

---

## Etapa 03 — Hacerlo implementable

> Esto es lo que separa un demo de un piloto que la empresa puede aprobar.

Cinco frentes: **Seguridad, Tests, Manejo de errores, Observabilidad, Costos.**

### Seguridad desde el primer commit
- **Secrets fuera del repo** — API keys en variables de entorno, nunca en el frontend ni subidas a GitHub.
- **Permisos por usuario** — Row Level Security en Supabase para que cada sede vea solo sus citas.
- **Datos sintéticos** — nada de datos reales de pacientes; si los hay, anonimizados.
- **Consentimiento** — el paciente acepta recibir mensajes por WhatsApp, como pide la Ley 1581 de datos personales.
- **Entradas validadas** — validar lo que escribe el paciente y lo que responde el modelo, y cuidarse del prompt injection.

*Cómo revisarlo rápido:* `/security-review` en Claude Code sobre tu repo · el Security Advisor de Supabase para ver tablas sin RLS · pedirle a Codex que busque secrets expuestos antes de hacer público el repo.

### Tests posibles en un fin de semana
- **Vitest → la lógica crítica** — el cálculo de riesgo y la reasignación de cupos, con casos borde (ej. dos pacientes para el mismo cupo).
- **Playwright → el flujo de punta a punta** — un test que agenda, cancela y verifica que el cupo pasó a la lista de espera.
- **Evals → la parte de IA** — veinte mensajes de pacientes con la respuesta esperada, para medir si un cambio de prompt mejora o empeora.
- **GitHub Actions → CI en cada push** — los tests corren solos y el badge en el README muestra que pasan.

*Atajo:* pídele a Claude o Codex que escriba los tests desde el PRD, y revísalos tú.

### Los otros frentes
- **Manejo de errores** — qué pasa cuando falla una API o el modelo responde algo raro.
- **Observabilidad** — logs y alertas para saber qué pasó sin tener que adivinar.
- **Costos** — cuánto cuesta cada uso del modelo y cuánto sería al mes en la operación real.

---

## Etapa 04 — Un demo que no se rompa

> Lo que muestras el domingo tiene que funcionar aunque falle el wifi, la API o los nervios.

- **Deploy en Vercel** — un link público desde el primer día, probado en el mismo entorno en el que vas a presentar.
- **Datos realistas** — generados con IA, con sedes, horarios y pacientes creíbles; nada de "usuario1" y "usuario2".
- **Video de respaldo** — grabado con Cap, listo por si algo falla en vivo.

---

## Etapa 05 — El pitch para quien decide

> Le hablas a alguien que después tiene que justificar adentro por qué implementarlo.

| La estructura | Aplicada a Sanamar |
|---------------|--------------------|
| 1. El problema de la empresa | 8.800 citas perdidas al mes, concentradas en primeras citas con especialista |
| 2. La solución en acción | Demo del panel de riesgo y del flujo de confirmación por WhatsApp |
| 3. El impacto esperado | Más agenda ocupada con el mismo equipo de call center |
| 4. Qué se necesita para implementarlo | Piloto en una sede con CSV y WhatsApp oficial, ya con tests, RLS y costo mensual estimado |

*Slides con Gamma o Claude · README claro, que suele ser lo primero que revisa el equipo técnico.*

---

## ✅ Checklist final (lo que debe estar listo)

- [ ] El problema real escrito en tres líneas
- [ ] El flujo principal funciona de punta a punta
- [ ] Secrets fuera del repo y RLS activo
- [ ] Datos sintéticos, nunca reales
- [ ] Qué pasa cuando algo falla, resuelto o documentado
- [ ] Tests del flujo principal pasando en CI
- [ ] Costo mensual estimado en la operación real
- [ ] Link desplegado y probado en otro dispositivo
- [ ] Video de pitch
- [ ] README con arquitectura y cómo correrlo
