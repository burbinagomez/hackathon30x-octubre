# Spec 003 — OSM Overpass, normalización común y dedup en 4 niveles

**Slice:** 003 · **Rama:** `feature/003-osm-dedup` · **Tiempo:** sábado PM (≤ 4 h con los cortes de "Cuándo cortar"; completo, ~5 h)
**Depende de:** 002. **Desbloquea:** 004 (dataset con leads de dos fuentes), 005 (tablero por fuente), 006 (enriquecer leads de OSM).

> Este slice **adelanta el cifrado del contacto** que el 002 dejó para el 006. Es el primer slice que persiste teléfono y correo (los de OSM), y el principio VI no admite guardarlos en claro "hasta el 006". El 006 reutiliza `Cifrador` y el catálogo; no los crea.

## Para quién
- **La pyme usuaria (o Dapta operando por ella):** el mismo ICP ahora trae también los negocios chicos que Supersociedades no ve (tiendas, restaurantes, ferreterías), muchos con teléfono publicado, sin duplicar la empresa que aparece en las dos fuentes. En BR y PE es la única fuente de descubrimiento.
- **El equipo:** la normalización y el dedup quedan en el dominio, como funciones puras, y cualquier fuente nueva los hereda.

## Qué hace
- Un segundo adaptador de `FuenteDescubrimiento`, `osm_overpass`, que busca por ciudad + tipo de negocio en Overpass.
- La selección de fuentes por ICP: el orquestador manda a cada fuente solo los criterios que declara en `filtros`, traduce CIIU → etiqueta OSM con `config/actividades.yaml` y reporta lo que ignoró.
- La normalización común (nombre, ciudad, dominio, teléfono E.164) para todas las fuentes.
- El dedup en 4 niveles de la skill `fuentes-publicas`: `id_fiscal + pais` → dominio → teléfono E.164 → nombre normalizado + misma ciudad, con `pg_trgm`. Lo dudoso va a una cola de revisión; no se fusiona a ciegas.
- El cifrado en reposo de `telefono` y `email`, con su HMAC para poder deduplicar sin descifrar.

## Puertos y adaptadores que toca (`config/fuentes.yaml`)
- **`fuentes_descubrimiento.osm_overpass`** (`habilitado: true`, `paises: [CO, MX, PE, BR, "*"]`, `filtros: [ciudad, tipo_negocio]`, `licencia: ODbL`): implementa `FuenteDescubrimiento`. Pasa de `sin_implementacion` a catálogo.
- **`fuentes_descubrimiento.croma_supersociedades_co`**: solo suma el mapeo de `geo` (que ya declara en `trae`); su salida pasa por la normalización común y el dedup nuevo.
- **`fuentes_descubrimiento.croma_dian_trade_co`**: sigue en `sin_implementacion`. Es extensión opcional si sobra tiempo (PRD §9) y no entra en "terminado cuando".
- **`limites.overpass_req_por_seg`** (1): lo hace cumplir un limitador en el adaptador.
- **`RegistroCostos` ← `postgres_costos`**: nuevo tipo de operación `overpass_query`.
- **`EmpresaCruda`** (del 002) suma `telefono_canal` y `email_canal`, opcionales con default `None`; los adaptadores del 002 no cambian de firma.
- **`RepositorioLeads`** (puerto del 002) suma `por_dominio`, `por_telefono` y `candidatos_por_nombre` (los tres devuelven lista) y `registrar_revision`.
- **Archivo nuevo `config/actividades.yaml`**: tabla de equivalencias CIIU → etiquetas OSM. No es un registro de adaptadores; es dato de dominio que vive en config para cambiarlo sin tocar código.
- **Archivo nuevo `config/dedup.yaml`**: `hosts_compartidos`, los hosts que no identifican a una empresa y quedan fuera de la regla 2. Mismo criterio que `actividades.yaml`: se agrega un host sin tocar código.

## Skills que aplican
- `fuentes-publicas`: Overpass (≤1 req/s, `[timeout:25]`, User-Agent identificable, área acotada), `EmpresaCruda`, E.164 con `phonenumbers`, actividad = código + sistema, los 4 niveles del dedup con sus umbrales.
- `cumplimiento-datos`: `tipo_titular=desconocido` para OSM (se trata como natural: no contactable hasta verificarlo en el 006), fila en `cumplimiento` con licencia ODbL, cifrado AES-GCM y catálogo de columnas sensibles.
- `libro-costos`: `overpass_query` con unidades = segundos y `computo_seg_usd`; prorrateo por lote.
- `slice-tdd`.

## Evals
Ninguno: este slice no usa IA. Las empresas de OSM + Supersociedades alimentan `backend/evals/dataset.json` en el 004.

## Flujo principal
1. `uv run python -m app.cli buscar --tenant <id> --pais CO --ciiu 4711 --departamento 11 --ciudad "Bogotá"` crea la `busqueda`.
2. `seleccionar_fuentes(registro, criterios, actividades)` (dominio, puro) decide, por cada fuente habilitada e implementada:
   - **País:** está en `paises` o `paises` incluye `"*"`.
   - **Actividad:** si la fuente filtra por `ciiu`, va directo. Si filtra por `tipo_negocio`, se traduce con `config/actividades.yaml`; sin mapeo, la fuente se ignora con motivo `sin_mapeo_actividad`.
   - **Geografía:** al menos una de las del ICP (`departamento`, `ciudad`) está en `filtros`; si no, se ignora con motivo `sin_geografia`.
   - Los criterios del ICP que la fuente no declara (p. ej. `departamento` para OSM, `ciudad` para Supersociedades) no se le pasan y quedan en `ignorados` del reporte.
   - Resultado con el ICP del ejemplo: Supersociedades recibe `ciiu + departamento`; OSM recibe `ciudad + tipo_negocio=[shop=supermarket, shop=convenience]`.
3. El adaptador OSM:
   - espera lo que pida el limitador (≤1 req/s);
   - arma **una** query Overpass (unión de las etiquetas), con `[out:json][timeout:25]`, área = ciudad dentro del país y tope de 500 elementos;
   - hace el `POST` con User-Agent identificable y registra la fila de `overpass_query` con los segundos medidos, por cada intento;
   - parsea a `EmpresaCruda`: descarta y cuenta los elementos sin `name`; marca `truncado` si llegaron 500.
4. `EjecutarBusqueda` normaliza cada `EmpresaCruda` y le aplica `resolver_duplicado` (dominio, puro, con el repo por puerto). Gana la primera regla que coincide:
   1. `(pais, id_fiscal)`;
   2. dominio del sitio web, salvo los hosts de `config/dedup.yaml` (y sus subdominios), que no cuentan;
   3. teléfono E.164 (vía HMAC);
   4. nombre normalizado + misma ciudad normalizada, con similitud `pg_trgm`. La fusión automática exige similitud ≥ 0,92 **y** geo en los dos **y** distancia ≤ 250 m; si falta cualquiera de las tres, el par va a revisión. Una sola regla, con o sin `id_fiscal`.

   Cada regla devuelve una **lista** de candidatos. Un candidato con `id_fiscal` distinto queda **vetado**: se excluye y la evaluación sigue con el siguiente candidato y, si no quedan, con la regla siguiente. En las reglas 1 a 3 gana el primer candidato no vetado por `creado_en` ascendente (el lead más viejo). En la regla 4 gana el primer candidato no vetado, en orden de similitud desc y `creado_en` asc, **que cumple fusión**; si ninguno la cumple, `revisar` con el primero de ese orden; si no queda ninguno, `nuevo`.

   El resultado es `fusionar(lead, regla)`, `revisar(lead, similitud)` o `nuevo`.
   - **Fusionar:** se completan los nulos del lead (`coalesce`); teléfono y email se tratan como par (dato, canal) y queda el de mayor confianza (`whatsapp_comercial` > `sitio_web` > `osm_contacto` > `whatsapp_osm`; empate → el que ya estaba), así que el canal sube y nunca baja; `tipo_titular` sube de `desconocido` a lo que diga el registro y nunca baja, se agrega `lead_fuentes`, y `cumplimiento` no cambia.
   - **Revisar:** se inserta como lead nuevo (con su `cumplimiento`) y se agrega una fila `pendiente` en `revision_dedup` con los dos leads y la similitud.
   - **Nuevo:** como en el 002.
5. El repositorio cifra `telefono` y `email` antes de escribir y calcula `telefono_hmac`. El dominio nunca ve bytes cifrados.
6. Si una fuente lanza `FuenteNoDisponible`, lo que trajeron las otras se persiste igual y la CLI la reporta como caída.
7. La CLI imprime el resumen **por fuente**: encontrados · nuevos · fusionados por regla (1/2/3/4) · en revisión · descartados sin nombre · truncado · criterios ignorados y fuentes ignoradas o caídas con su motivo.

## Terminado cuando (tests que hoy fallan)

**Registro y selección de fuentes**
- `backend/tests/unit/descubrimiento/test_registro.py::test_carga_config_fuentes_yaml_real_sin_error`: **se actualiza** a `sin_implementacion == {"croma_dian_trade_co"}` y el catálogo trae `osm_overpass`.
- `backend/tests/unit/descubrimiento/test_seleccion_fuentes.py`:
  - `::test_actividades_yaml_real_carga_y_mapea_4711`: el `config/actividades.yaml` del repo carga y `4711 → {"shop=supermarket", "shop=convenience"}`.
  - `::test_icp_colombia_completo_usa_las_dos_fuentes`: el ICP del flujo da Supersociedades con `{ciiu, departamento}` y OSM con `{ciudad, tipo_negocio}`; `departamento` queda en `ignorados` de OSM y `ciudad` en los de Supersociedades.
  - `::test_icp_sin_ciudad_ignora_osm_por_geografia`: con solo `departamento`, OSM queda ignorada con `sin_geografia` y Supersociedades corre.
  - `::test_ciiu_sin_mapeo_ignora_osm`: un CIIU que no está en `actividades.yaml` deja OSM ignorada con `sin_mapeo_actividad`.
  - `::test_icp_brasil_solo_usa_osm`: `pais=BR` + ciudad + CIIU mapeado → solo OSM; Supersociedades ignorada por país.
  - `::test_criterio_no_declarado_no_llega_al_adaptador`: `ingresos_min` en el ICP llega a Supersociedades y no a OSM. El adaptador falso de OSM lanza `CriterioNoSoportado` si lo recibe, así que el test falla si el filtro no ocurre.

**Contrato del puerto** (`backend/tests/contratos/test_fuente_descubrimiento.py`)
- Los tres tests del 002 corren también con `[osm_overpass]`, con transporte falso. Lo único nuevo es el parámetro; la suite no se toca.

**Adaptador OSM** (`backend/tests/unit/descubrimiento/test_osm_overpass.py`, fixture **sintética** con teléfonos CO válidos para `phonenumbers`)
- `::test_query_acotada_con_timeout_y_tope`: el cuerpo enviado contiene `[out:json][timeout:25]`, `"ISO3166-1"="CO"`, `"name"="Bogotá"`, una rama por etiqueta (`["shop"="supermarket"]`, `["shop"="convenience"]`), el filtro `["name"]` y `out center tags 500`.
- `::test_envia_user_agent_identificable`: el header `User-Agent` empieza por `dapta-reto-30x/` y contiene la URL del repo.
- `::test_mapea_elemento_a_empresa_cruda`:
  - `nombre`, `direccion` (`addr:street` + `addr:housenumber`), `web` (`website` → `contact:website` → `url`), `email` (`email` → `contact:email`), `geo` (`lat/lon` del nodo o `center` del `way`);
  - `telefono` en E.164 desde `phone` → `contact:phone` → `mobile` → `contact:mobile`, separando por `;` y quedándose con el primero válido: `"601 234 5678; 300 123 4567"` → `"+576012345678"`;
  - `ciudad` = `addr:city` y, si falta, la ciudad buscada;
  - `url_origen == "https://www.openstreetmap.org/node/123"` (y `way/…` para un `way`, con `center` como geo);
  - `licencia == "ODbL"`, `as_of` = `osm3s.timestamp_osm_base`, `tipo_titular == "desconocido"`, `actividad == ("shop=supermarket", "OSM")`, `id_fiscal is None`;
  - `telefono_canal == "osm_contacto"` y `email_canal == "osm_contacto"`; sin teléfono o sin correo, el canal respectivo es `None`.
- `::test_elemento_sin_nombre_se_descarta_y_se_cuenta`: 3 elementos, 1 sin `name` → 2 empresas y `descartados_sin_nombre == 1`.
- `::test_telefono_invalido_queda_nulo`: `phone="123"` → `telefono is None`, la empresa se devuelve igual.
- `::test_web_en_host_compartido_no_se_guarda`: `website="https://facebook.com/latienda"` → `web is None`.
- `::test_web_wa_me_pasa_a_telefono`: `website="https://wa.me/573001234567"` y sin `phone` → `web is None`, `telefono == "+573001234567"` y `telefono_canal == "whatsapp_osm"`; con `phone="123"` (inválido) → igual, gana el de `wa.me` con `whatsapp_osm`; con un `phone` válido, el `phone` gana con `osm_contacto` y el número de `wa.me` se descarta.
- `::test_quinientos_elementos_marca_truncado`: con 500 elementos, `truncado is True`; con 499, `False`.
- `::test_limitador_espera_un_segundo_entre_requests`: con reloj y `sleep` falsos, dos búsquedas seguidas hacen que el segundo request espere ≥ 1 s; si pasaron 1,5 s, no espera.
- `::test_registra_segundos_de_cada_intento`: un 429 con `Retry-After: 5` seguido de un 200. El transporte falso avanza el reloj 2 s y 3 s durante cada request, y el `sleep` falso lo avanza lo que se le pide (5 s de `Retry-After` + lo del limitador). Resultado: 2 requests y 2 filas con `tipo="overpass_query"`, `unidades` **2 y 3** (no 7 ni 8: la espera no se cobra como cómputo), `costo_unitario == Decimal("0.0000070")`, `proveedor="osm"`, `fuente="osm_overpass"`, `lead_id=None`, `gratis=False` y el `lote_id` de la corrida; el `sleep` recibió 5.
- `::test_retry_after_tiene_tope_de_diez_segundos`: `Retry-After: 120` → el `sleep` recibe 10.
- `::test_segundo_fallo_se_reporta_sin_tragarlo`: dos 504 seguidos (sin `Retry-After`) lanzan `FuenteNoDisponible`, quedan 2 filas de costo, el `sleep` entre los dos recibió `max(1, limitador)`, y el mensaje de la excepción no incluye el cuerpo de la respuesta.

**Adaptador Croma, geo** (`backend/tests/unit/descubrimiento/test_croma_supersociedades.py`)
- `::test_mapea_geo`: la fixture del 002 suma `lat/lon` y la `EmpresaCruda` trae `geo`; sin esos campos, `geo is None`.
- `::test_registro_no_trae_canal_publicado`: `telefono_canal` y `email_canal` son `None` (un dato del registro no es canal publicado, skill `cumplimiento-datos`).

**Normalización** (`backend/tests/unit/descubrimiento/test_normalizacion.py`, dominio puro)
- `::test_normaliza_nombre`: `"Panadería La Espiga S.A.S."` → `"panaderia la espiga"`; `"ALMACENES ÉXITO S.A."` → `"almacenes exito"`; `"Ferretería & Cía. Ltda"` → `"ferreteria"`; `"Abarrotes Lupita S.A. de C.V."` → `"abarrotes lupita"`; `"Bodega Sol S.A.C."` → `"bodega sol"`.
- `::test_normaliza_ciudad`: `"BOGOTÁ D.C."`, `"Bogotá, Distrito Capital"` y `"bogota"` → `"bogota"`; `"Medellín"` → `"medellin"`.
- `::test_normaliza_dominio`: `"https://WWW.Tienda.com.co:443/contacto"` → `"tienda.com.co"`; `"tienda.com.co"` (sin esquema) → igual.
- `::test_dedup_yaml_real_carga_hosts_compartidos`: el `config/dedup.yaml` del repo carga y `hosts_compartidos` incluye `facebook.com`, `wa.me` y `sites.google.com`.
- `::test_dominio_compartido_no_sirve_para_dedup`: con los hosts del YAML real, `facebook.com/latienda`, `m.facebook.com/latienda`, `instagram.com/x`, `wa.me/57300…`, `linktr.ee/x`, `sites.google.com/view/x` → `None`; `tiendafacebook.com` → `"tiendafacebook.com"` (sufijo de host, no de texto).
- `::test_telefono_a_e164`: con región `CO`, `"300 123 4567"` → `"+573001234567"`, `"+57 (601) 234-5678"` → `"+576012345678"`, `"abc"` → `None`.
- `::test_mismo_numero_con_y_sin_indicativo_da_el_mismo_e164`: `"3001234567"`, `"+57 300 123 4567"` y `"57 300 123 4567"` → `"+573001234567"` los tres. (El mismo HMAC se prueba en `test_cifrador.py`.)
- `::test_distancia_en_metros`: haversine entre dos puntos de Bogotá a ~100 m da entre 95 y 105.

**Dedup** (`backend/tests/unit/descubrimiento/test_dedup.py`, `resolver_duplicado` con repositorio falso)
- `::test_regla_1_mismo_id_fiscal_fusiona`.
- `::test_regla_2_mismo_dominio_fusiona`.
- `::test_regla_3_mismo_telefono_fusiona`.
- `::test_regla_4_nombre_similar_misma_ciudad_fusiona`: el repo falso devuelve un candidato con similitud 0.95, los dos con geo a 50 m → `fusionar(lead, regla=4)`.
- `::test_host_compartido_no_fusiona_por_regla_2`: dos empresas sin NIT ni teléfono, con nombres distintos y `web` = `https://facebook.com/tiendauno` y `https://facebook.com/tiendados` (normalizadas con los hosts del YAML real) → la segunda da `nuevo` y el repo falso no recibió `por_dominio`. Control en el mismo test: con `https://tienda.com.co/uno` y `https://tienda.com.co/dos` → `fusionar(lead, regla=2)`, para que el test no pase por no llamar nunca a la regla.
- `::test_dominio_gana_sobre_telefono`: el dominio coincide con el lead A y el teléfono con el lead B → se fusiona con A, regla 2.
- `::test_id_fiscal_distinto_nunca_fusiona`: mismo dominio y mismo teléfono, pero NIT distinto en los dos → `nuevo`, sin fila en revisión.
- `::test_veto_excluye_candidato_y_sigue_con_la_regla_siguiente`: el dominio coincide con A (NIT distinto) y el teléfono con B (sin NIT) → `fusionar(B, regla=3)`.
- `::test_veto_sigue_con_el_siguiente_candidato_de_la_misma_regla`: `por_dominio` devuelve [A (NIT distinto), C (sin NIT)] → `fusionar(C, regla=2)`.
- `::test_desempate_por_creado_en`: `por_telefono` devuelve dos leads sin NIT → se fusiona con el de `creado_en` menor, sin importar el orden en que el repo falso los devuelva.
- `::test_homonimo_cercano_fusiona`: lead de Supersociedades (con NIT y geo) + OSM homónimo (sin NIT) a 120 m, similitud 1.0 → `fusionar(lead, regla=4)`.
- `::test_homonimo_lejano_va_a_revision`: el mismo par a 3 km → `revisar`, aunque la similitud sea 1.0.
- `::test_homonimo_sin_geo_va_a_revision`: el mismo par con `geo` nulo en cualquiera de los dos → `revisar`.
- `::test_borde_de_distancia`: 250 m → `fusionar`; 251 m → `revisar`.
- `::test_homonimos_osm_lejanos_van_a_revision`: dos leads OSM sin NIT, similitud 1.0, a 3 km → `revisar`; el mismo par a 100 m → `fusionar(lead, regla=4)`.
- `::test_regla_4_prefiere_candidato_fusionable_sobre_revision`: A (similitud 1.0, con NIT, a 3 km) y B (0.93, sin NIT, a 80 m) → `fusionar(B, regla=4)`.
- `::test_regla_4_ordena_por_similitud_y_despues_creado_en`: dos candidatos fusionables con la misma similitud → gana el de `creado_en` menor; con similitudes 0.95 y 0.97 → gana el de 0.97, sin importar el orden en que los devuelva el repo falso. Si ninguno es fusionable (0.97 y 0.90, los dos a 3 km, devueltos al revés), la revisión apunta al de 0.97.
- `::test_sin_ciudad_salta_regla_4`: empresa sin ciudad y nombre idéntico a un lead → `nuevo`, y el repo falso no recibió `candidatos_por_nombre`.
- `::test_misma_ciudad_es_requisito_de_regla_4`: el repo falso recibe la ciudad normalizada; el filtro real se prueba en integración.
- `::test_bordes_de_similitud`: `clasificar_similitud(0.92) == CANDIDATO_FUSION` (candidato: la regla 4 todavía exige geo y ≤ 250 m), `(0.9199) == REVISION`, `(0.85) == REVISION`, `(0.8499) == NUEVO`.
- `::test_revision_inserta_lead_nuevo_y_fila_pendiente`: con similitud 0.88 → 2 leads, 1 fila `revision_dedup` `pendiente` con `similitud == 0.88`, y cada lead con su `cumplimiento`.
- `::test_fusion_completa_nulos_sin_pisar`: lead de Supersociedades (con NIT, sin teléfono) + OSM (sin NIT, con teléfono y web) → el lead queda con NIT, teléfono y web; el nombre del registro no se pisa. El canal viaja con su dato: si el teléfono llega de OSM por `wa.me`, el lead queda con `telefono_canal == "whatsapp_osm"`. Caso cruzado: lead A con teléfono `osm_contacto` y sin email + lead B con email `osm_contacto` y teléfono `whatsapp_osm` → teléfono y canal de A, email de B con `osm_contacto`; nunca un dato de uno con el canal del otro.
- `::test_canal_sube_y_nunca_baja`: lead con teléfono `whatsapp_osm` + otro con teléfono `osm_contacto` → queda el par (teléfono, canal) `osm_contacto`; al revés → sigue `osm_contacto`. Regla 3 (mismo número): `whatsapp_osm` + `osm_contacto` → mismo teléfono, canal `osm_contacto`. Empate → el que ya estaba.
- `::test_tipo_titular_sube_y_nunca_baja`: lead OSM `desconocido` + Supersociedades `juridica` → `juridica`; al revés (lead `juridica` + OSM `desconocido`) → sigue `juridica`.
- `::test_fusion_no_toca_cumplimiento`: tras fusionar, la fila de `cumplimiento` es la original y `lead_fuentes` tiene las 2 fuentes con sus licencias.

**Cifrado (principio VI)** (`backend/tests/arquitectura/test_cifrado.py`, contra Postgres de prueba)
- `::test_columnas_sensibles_cifradas`: por cada `(tabla, columna)` de `backend/app/seguridad/catalogo_sensibles.py`, guarda un valor vía repositorio, lo lee crudo con SQL y verifica que no contiene el texto en claro y que `Cifrador.descifrar` devuelve el original.
- `::test_ninguna_columna_de_contacto_fuera_del_catalogo`: recorre `information_schema.columns`; toda columna cuyo nombre contenga `telefono`, `email`, `correo`, `contacto` o `respuesta` está en el catálogo, termina en `_hmac`, o es una de las columnas de canal de una lista cerrada (`leads.telefono_canal`, `leads.email_canal`: etiqueta de origen con `CHECK`, no el dato). Una `contacto_canal` nueva falla. Falla si alguien agrega `leads.telefono` en claro.
- `::test_contacto_no_aparece_en_logs`: corre `EjecutarBusqueda` con la fixture OSM (`phone="300 123 4567"`, `website="https://wa.me/573009876543"`, `email="ventas@ejemplo.co"`) y `caplog` en `DEBUG` sobre todos los loggers (incluido `httpx`), y verifica que ninguna de estas formas aparece en ningún registro: `+573001234567`, `3001234567`, `300 123 4567`, `573009876543`, `ventas@ejemplo.co`.
- `::test_contacto_no_queda_en_claro_en_columnas_no_catalogadas`: tras la misma corrida, el SQL crudo de `leads.web`, `leads.direccion` y `leads.nombre` no contiene `3001234567` ni `3009876543`. Cubre el `wa.me` que el test de catálogo no ve porque la columna se llama `web`.
- `backend/tests/unit/seguridad/test_cifrador.py`:
  - `::test_ida_y_vuelta`;
  - `::test_mismo_texto_da_cifrado_distinto` (nonce aleatorio);
  - `::test_aad_de_otra_columna_no_descifra`: un valor cifrado para `leads.telefono_cifrado` no descifra como `leads.email_cifrado`;
  - `::test_hmac_es_determinista_y_distinto_de_la_clave_de_cifrado`;
  - `::test_mismo_numero_con_y_sin_indicativo_da_el_mismo_hmac`: las tres formas de `test_mismo_numero_con_y_sin_indicativo_da_el_mismo_e164`, pasadas por `a_e164` y luego por el HMAC, dan el mismo valor;
  - `::test_falla_sin_cifrado_key`: sin `CIFRADO_KEY` en el entorno, la app no arranca (`ConfigInvalida`).

**Integración** (Postgres de prueba, rol `app_rt`)
- `backend/tests/integration/test_dedup_repo.py`, con `pg_trgm` real:
  - `::test_canal_null_si_y_solo_si_dato_null`: `INSERT` de un lead con `telefono_cifrado` y sin `telefono_canal`, o al revés, falla por `CHECK`; lo mismo con el email. Nace rojo con la `0003` sin los `CHECK` de dato ⇔ canal; pasa a verde al agregarlos.
  - `::test_check_de_canales`: `telefono_canal` acepta `whatsapp_comercial`, `sitio_web`, `osm_contacto` y `whatsapp_osm`, y rechaza cualquier otro; `email_canal` rechaza `whatsapp_osm` y `whatsapp_comercial`. Nace rojo con la `0003` sin los `CHECK` de canal.
  - `::test_nombre_identico_tras_normalizar_es_candidato_de_fusion`: `"supermercado la economia"` vs el mismo → similitud 1.0.
  - `::test_plural_largo_cae_en_fusion`: `"distribuidora de alimentos la sabana"` vs `"distribuidoras de alimentos la sabana"` → ≥ 0.92.
  - `::test_plural_corto_cae_en_revision`: `"supermercado la economia"` vs `"supermercados la economia"` → en [0.85, 0.92).
  - `::test_nombres_distintos_no_son_candidatos`: `"ferreteria el tornillo"` vs `"ferreteria el martillo"`, y `"autoservicio la 80"` vs `"autoservicio la 85"` → ninguno devuelto.
  - `::test_mismo_nombre_otra_ciudad_no_es_candidato`.
  - `::test_por_telefono_encuentra_por_hmac`: el lead guardado con `+573001234567` se encuentra por ese número y no por `+573001234568`.
  - `::test_por_dominio_devuelve_todos_los_que_coinciden`: dos leads con el mismo dominio → los dos, para que el dominio aplique veto y desempate.
  - `::test_par_de_revision_no_se_duplica_invertido`: registrar `(A, B)` y después `(B, A)` deja una sola fila.
  - Los valores de los pares salen de una emulación de `pg_trgm`; el test fija la **banda**, no el número exacto. Si Postgres real los ubica distinto, se cambia el par, no el umbral.
- `backend/tests/integration/test_busqueda_dos_fuentes.py`:
  - `::test_supersociedades_y_osm_dan_un_lead`: `"SUPERMERCADO LA ECONOMÍA S.A.S."` en `"BOGOTÁ D.C."` (Supersociedades, NIT 900123456, geo de la fixture) + `"Supermercado La Economía"` en Bogotá a 120 m (OSM, con teléfono) → 1 lead con 2 `lead_fuentes`, `tipo_titular='juridica'`, `id_fiscal='900123456'`, `telefono_cifrado` no nulo y 1 `cumplimiento`.
  - `::test_orden_de_fuentes_no_cambia_el_resultado`: OSM primero y Supersociedades después da el mismo lead (fusión por regla 4, NIT completado, `tipo_titular` sube a `juridica`).
  - `::test_homonimo_lejano_no_hereda_el_telefono`: el mismo par con el nodo OSM a 3 km → 2 leads y 1 `revision_dedup` pendiente; el lead `juridica` queda con `telefono_cifrado` nulo.
  - `::test_osm_caido_no_pierde_supersociedades`: el transporte OSM devuelve 504 dos veces → los leads de Supersociedades se persisten y el resumen marca `osm_overpass` como caída.
- `backend/tests/integration/test_costos_repo.py::test_overpass_query_escribe_fila_en_costos`: el adaptador, con transporte y reloj falsos y `postgres_costos` real, deja 1 fila `overpass_query` con `unidades == Decimal(2)` (el reloj falso avanza 2 s durante el request), `costo_unitario = Decimal("0.0000070")` leído como `numeric`, `gratis=false` y el `tenant_id` del contexto. Es el chequeo del principio VIII.
- `backend/tests/integration/test_rls.py::test_tenant_b_no_accede_a_datos_de_a[revision_dedup]`: se suma la tabla nueva al parametrizado del 002.
- `backend/tests/arquitectura/test_migraciones.py::test_pg_trgm_disponible_sin_superusuario`: después de `upgrade head` con `app_mig` (sin `SUPERUSER`), `app_rt` puede llamar a `similarity('a','a')` sin calificar el esquema, y `pg_extension` muestra `pg_trgm` en el esquema `extensions`, no en `public`. En Supabase la extensión ya está en `extensions` desde la tarea 0a del 001 (rama `feature/001-walking-skeleton`, `plan.md` y `quickstart.md`). En CI, `supabase_simulado.sql` la crea igual que Supabase: `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions`, como superusuario. Se resuelve por el `search_path = public, extensions` y el `USAGE` sobre `extensions` que pone `roles.sql` del 001. Nace rojo: hasta que la tarea 4 amplía el script, `similarity()` no existe en CI.
## Fuera del alcance
- **DIAN Trade** (`croma_dian_trade_co`): opcional si sobra tiempo; si se hace, `sin_implementacion` pasa a `set()` en el mismo PR.
- **006:** `contactable`, verificación de `tipo_titular` de los leads de OSM contra RUES, descarte de correos nominales y enriquecimiento por sitio web. Los leads solo-OSM quedan `desconocido` y **no son contactables** hasta ahí. El 006 hereda `telefono_canal`/`email_canal` tal como los deja este slice: el teléfono del sitio propio (`sitio_web`) reemplaza a uno `osm_contacto` o `whatsapp_osm`, y nunca al revés.
- **005:** pantalla de la cola de revisión, tablero por fuente y prorrateo. Acá la cola se llena y se cuenta en la CLI; resolverla queda manual (SQL) hasta que haya pantalla.
- **007:** no contacta leads con una `revision_dedup` pendiente. Se deja escrito como contrato para su spec.
- Caché de Overpass: no se cachea (ver Decisiones técnicas).
- SCIAN (MX) y CNAE (BR) en `actividades.yaml`: solo CIIU esta vez.
- Rotación de `CIFRADO_KEY`.
- Paginación de Overpass: el tope de 500 se reporta como `truncado`.

## Decisiones técnicas

**Módulo** `backend/app/modulos/descubrimiento/`:
- `dominio/`:
  - `normalizacion.py`: `normalizar_nombre`, `normalizar_ciudad`, `normalizar_dominio`, `a_e164`. Usa `phonenumbers` (librería pura, sin I/O; se permite en dominio y se declara en el contrato de import-linter).
  - `dedup.py`: `resolver_duplicado`, `clasificar_similitud`, `UMBRAL_FUSION = 0.92`, `UMBRAL_REVISION = 0.85`.
  - `seleccion.py`: `seleccionar_fuentes`.
- `infraestructura/adaptadores/osm_overpass.py`.
- `backend/app/seguridad/{cifrado.py,catalogo_sensibles.py}`: fuera del módulo, porque lo usan todos.

**Overpass:**
- Query:
  ```
  [out:json][timeout:25];
  area["ISO3166-1"="CO"][admin_level=2]->.pais;
  rel(area.pais)["name"="Bogotá"]["boundary"="administrative"];
  map_to_area->.ciudad;
  ( nwr(area.ciudad)["shop"="supermarket"]["name"];
    nwr(area.ciudad)["shop"="convenience"]["name"]; );
  out center tags 500;
  ```
- URL por constante (`https://overpass-api.de/api/interpreter`) con override `OVERPASS_URL` en el entorno.
- User-Agent `dapta-reto-30x/<versión> (+<URL del repo público>)`.
- `httpx` con timeout de 30 s (el `[timeout:25]` del servidor + margen). Un reintento ante 429 o 504, respetando `Retry-After` con tope de 10 s; sin `Retry-After`, espera 1 s o lo que pida el limitador, lo que sea mayor.
- Limitador en el adaptador, con reloj y `sleep` inyectables. `# ponytail:` limitador por proceso; con varios workers pasa a un contador compartido.
- `mobile` y `contact:mobile` se leen porque en OSM son el móvil **del negocio** y Dapta califica por llamada: sin teléfono, el lead no es calificable.
- `web` en un host de `hosts_compartidos` (`config/dedup.yaml`, el cargador de `aplicacion/` se lo inyecta al adaptador como `frozenset`; el adaptador no lee config) **no se guarda**: no identifica a la empresa y, en `wa.me`/`api.whatsapp.com`, la URL *es* un teléfono en claro (principio VI). El número de `wa.me` pasa por `a_e164` y va a `telefono` si no hay otro teléfono válido; si lo hay, se descarta. El mapeo del adaptador lo hace con `normalizar_dominio` del dominio, no con lógica propia.
- `# ponytail:` se guarda solo el primer teléfono válido; si el 006 necesita más, se agrega `lead_telefonos`.

**Canal publicado:** cada dato de contacto lleva de dónde salió, en `telefono_canal` y `email_canal` (tipo `CanalPublicado` en el dominio, `CHECK` en la tabla):

| Valor | Origen | Confianza |
|---|---|---|
| `whatsapp_comercial` | enlace `wa.me`/`api.whatsapp.com` en el sitio propio de la empresa (lo escribe el 006) | alta; gana sobre `sitio_web` porque además habilita el WhatsApp asistido con opt-in (009) |
| `sitio_web` | el sitio propio de la empresa (lo escribe el 006) | alta |
| `osm_contacto` | tag `phone`/`contact:*`/`mobile`/`email` del elemento OSM | media |
| `whatsapp_osm` | número sacado de un `website` `wa.me`/`api.whatsapp.com` en OSM | baja |

`whatsapp_osm` es la más baja porque es una URL que alguien cargó en el campo web, no un tag de contacto, y puede ser el WhatsApp personal del tendero. Igual **cuenta como canal publicado** (decisión del usuario): el negocio lo publicó en OSM. **No hay detección automática de teléfono nominal** (la regla 3 de la skill solo ve teléfonos etiquetados como personales, y un `wa.me` nunca trae esa etiqueta): el riesgo se acepta con confianza baja, y el 006 lo reemplaza por `sitio_web` solo cuando lo encuentra. Contar como canal habilita la llamada, no el WhatsApp (que exige opt-in). `email_canal` nunca es `whatsapp_osm` ni `whatsapp_comercial` (`CHECK`). El `CHECK` de `telefono_canal` admite los cuatro valores desde la `0003`, aunque esta spec no escriba `whatsapp_comercial`: así la 006 y la 009 no necesitan migrar el `CHECK`. Dato y canal son NULL juntos (`CHECK ((telefono_cifrado IS NULL) = (telefono_canal IS NULL))`, ídem email). Un dato del registro (Supersociedades) no tiene canal: el registro no es canal publicado. La regla `contactable` (skill `cumplimiento-datos`, 006) se evalúa sobre estos dos campos; acá solo se etiqueta.

**Sin caché para Overpass:** la respuesta cruda trae teléfonos y correos, y `fuente_cache` los dejaría en claro (principio VI). Overpass es gratis y la regla de 1 req/s la cumple el limitador. `# ponytail:` si Overpass nos limita en la demo, caché con `respuesta_cifrada`.

**Selección de fuentes:** función pura que lee `paises`/`filtros` del registro, no un método nuevo en cada adaptador. El adaptador sigue lanzando `CriterioNoSoportado` (contrato del 002) como red de seguridad. El cargador de `config/actividades.yaml` vive en `aplicacion/`, junto a `cargar_registro` (como en el 002); el dominio recibe solo el `dict`.

**`config/actividades.yaml`:**
```yaml
# CIIU Rev. 4 A.C. (DANE) → equivalentes por sistema. Una fuente que filtra
# por tipo_negocio sin mapeo para el CIIU del ICP se ignora y se reporta.
"4711":
  descripcion: "Comercio al por menor en establecimientos no especializados, surtido principalmente de alimentos"
  osm: ["shop=supermarket", "shop=convenience"]
"5611":
  descripcion: "Expendio a la mesa de comidas preparadas"
  osm: ["amenity=restaurant"]
"4752":
  descripcion: "Comercio al por menor de artículos de ferretería, pinturas y vidrios"
  osm: ["shop=hardware"]
```

**Normalización:**
- Nombre: NFKD sin tildes, minúsculas, sin puntuación, sin sufijos societarios de una lista cerrada (`s.a.s.`, `sas`, `ltda`, `s.a.`, `sa`, `s.a. de c.v.`, `sa de cv`, `s.a.c.`, `sac`, `e.u.`, `& cia`, `y cia`, `cia`), espacios colapsados.
- Ciudad: igual, más `d.c.`, `dc` y `distrito capital`.
- Dominio: host en minúscula, sin `www.` ni puerto. Si el host es uno de `hosts_compartidos` o un subdominio suyo (`host == h or host.endswith("." + h)`), `normalizar_dominio` devuelve `None`: no se guarda en `leads.dominio` y la regla 2 no lo ve. Razón: miles de negocios comparten esos hosts, y deduplicar por ellos fusionaría empresas distintas. La lista vive en `config/dedup.yaml`; el cargador está en `aplicacion/` y el dominio recibe un `frozenset`:
  ```yaml
  # Hosts que comparten muchos negocios: no identifican a una empresa.
  # Un sitio en uno de estos hosts (o un subdominio) no se guarda como dominio
  # y no cuenta para la regla 2 del dedup.
  hosts_compartidos:
    - facebook.com
    - instagram.com
    - wa.me
    - api.whatsapp.com
    - linktr.ee
    - sites.google.com
    - linkedin.com
    - tiktok.com
    - x.com
    - twitter.com
    - google.com
    - goo.gl
    - bit.ly
  ```
  `# ponytail:` sin publicsuffix; si aparece otro host compartido, se agrega al YAML.
- E.164 con `phonenumbers.parse(valor, region=pais)` y `is_valid_number`.

**Dedup:**
- Una cadena con un solo dominio o un solo teléfono queda como **un lead**. Es la decisión correcta para prospectar: un punto de contacto, una llamada.
- `id_fiscal` distinto en los dos → nunca se fusionan, por ninguna regla. Son personas jurídicas distintas. El veto excluye al candidato, no corta la búsqueda: el siguiente candidato o la siguiente regla todavía pueden coincidir.
- `por_dominio`, `por_telefono` y `candidatos_por_nombre` devuelven **listas** (los índices no son únicos). El desempate lo hace el dominio, no el `ORDER BY` del repo, para que el test unitario lo pruebe.
- **Regla 4, siempre con geo:** fusión automática solo con similitud ≥ `UMBRAL_FUSION`, geo en los dos y distancia ≤ `DISTANCIA_MAX_FUSION_M = 250`, tenga o no `id_fiscal` alguno de los dos. Razón: en una ciudad hay muchas tiendas independientes con el mismo nombre. Fusionar el nodo OSM con la sociedad le pegaría el móvil de un tendero (posible persona natural) a un lead `juridica`, que en el 006 se vuelve contactable (principio VII); y fusionar dos homónimos OSM sin NIT deja un lead que, si el 006 verifica uno contra RUES, hereda el contacto del otro. 250 m cubre el error típico de geocodificar una dirección de registro contra la posición del nodo, y deja fuera la tienda de la otra cuadra. Sin geo o más lejos → revisión, del lado seguro.
- Distancia con haversine en `dominio/geo.py` (stdlib `math`).
- La similitud la calcula Postgres (`similarity()` de `pg_trgm`, con índice GIN `gin_trgm_ops` sobre `nombre_normalizado` y `ciudad_normalizada` por igualdad). El dominio solo clasifica el número con los umbrales. `# ponytail:` `similarity() >=` no usa el índice GIN; a esta escala da igual. Si crece, operador `%` con `pg_trgm.similarity_threshold`.
- `candidatos_por_nombre` devuelve los de `similitud ≥ UMBRAL_REVISION`; el dominio ordena por similitud desc y `creado_en` asc, y recorre la lista buscando el primero que cumple fusión antes de caer a revisión.
- `revision_dedup` guarda el par ordenado (`lead_a < lead_b`, con `CHECK`) para que `(A, B)` y `(B, A)` sean la misma fila.

**Cifrado:**
- AES-256-GCM (`cryptography`, dependencia nueva: la stdlib no trae AES). Nonce de 12 bytes como prefijo del `bytea`. AAD = `"tabla.columna"`, para que un valor no se pueda mover de columna.
- Dos subclaves derivadas por HKDF-SHA256 de `CIFRADO_KEY` (32 bytes en base64, del entorno): una para cifrar y otra para el HMAC-SHA256 del teléfono. El HMAC permite la regla 3 sin descifrar.
- El dominio maneja el E.164 en claro; `repositorio_leads` cifra y hashea al escribir y descifra al leer.
- Catálogo inicial: `leads.telefono_cifrado`, `leads.email_cifrado`. El 006 suma `nombre_contacto` y el 007 `respuesta_texto`.

**Tablas** (migración `supabase/migrations/0003_osm_dedup.sql`, a mano, con `GRANT` a `app_rt`):

| Tabla | Cambio |
|---|---|
| — | `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions`. Es un no-op en Supabase (tarea 0a) y en CI (`supabase_simulado.sql`); el esquema va explícito para que nunca caiga en `public`. Fuera de eso, nada califica el esquema: `similarity()` y `gin_trgm_ops` se resuelven por `search_path`. |
| `leads` | `+ nombre_normalizado`, `+ ciudad_normalizada`, `+ dominio` (nullable), `+ lat`, `+ lon` (`double precision`, nullable), `+ telefono_cifrado bytea`, `+ telefono_hmac bytea`, `+ email_cifrado bytea`, `+ telefono_canal`, `+ email_canal` (`text` nullable, `CHECK` contra los valores de la tabla de canales; `email_canal NOT IN ('whatsapp_osm', 'whatsapp_comercial')`; `telefono_canal` admite los cuatro valores; `(telefono_cifrado IS NULL) = (telefono_canal IS NULL)` e ídem email). Índices: GIN trigram sobre `nombre_normalizado`; btree sobre `(tenant_id, dominio)` y `(tenant_id, telefono_hmac)`, **no únicos** (la regla de prioridad decide en la app). |
| `revision_dedup` | `tenant_id`, `busqueda_id`, `lead_a`, `lead_b`, `similitud numeric(4,3)`, `estado` ∈ `pendiente`/`fusionado`/`separado`, `creado_en`. RLS como el resto. `CHECK (lead_a < lead_b)` + UNIQUE `(lead_a, lead_b)`. |

**Geo de Supersociedades:** `fuentes.yaml` declara `geo` en `trae`, pero el 002 no lo mapeó. Este slice suma `lat/lon` al mapeo del adaptador del 002 (si Croma los trae) y a la fixture. Si la corrida real del paso 10 muestra que Croma no trae geo, todo cruce por regla 4 cae a revisión: es el lado seguro y se reporta.

**Costos:** `overpass_query` con `unidades` = segundos **del request** (desde antes del `POST` hasta tener la respuesta), medidos con el reloj inyectable. La espera del limitador y la de `Retry-After` **no** se cuentan: es tiempo sin cómputo, y contarla haría el costo dependiente de la carga del servidor público. `costo_unitario = tarifas.computo_seg_usd`, `gratis=false` (el cómputo es nuestro aunque Overpass no cobre). Los intentos fallidos también registran sus segundos. El cargador de `tarifas.yaml` convierte con `Decimal(str(valor))`, para que el test compare `Decimal` con `Decimal` y no un float.

**Cumplimiento de un lead OSM:** `fuente='osm_overpass'`, `licencia='ODbL'`, `url_origen` del elemento, `as_of` de la base OSM, `base_legal` nula hasta el 007. La atribución "© OpenStreetMap contributors", con enlace a `/copyright`, se muestra en el tablero (005, en cuanto OSM aporta un lead) y en el README (013).

## Plan de tareas (TDD, en orden)
1. **Normalización, geo y `config/dedup.yaml`:** `test_normalizacion.py` en rojo → verde. El primero, `test_normaliza_nombre`.
2. **Selección de fuentes + `config/actividades.yaml`:** `test_seleccion_fuentes.py` en rojo → verde; el primero, el del YAML real.
3. **Cifrador:** `test_cifrador.py` en rojo → verde.
4. **Migración `0003`:** primero `test_pg_trgm_disponible_sin_superusuario` en rojo; después se suma `CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions` a `supabase_simulado.sql` y el test pasa a verde. Luego `test_rls[revision_dedup]` y `test_cifrado.py` (catálogo y columnas) en rojo → verde. El **advisor revisa los tests de RLS y de cifrado antes de aceptarlos**.
5. **Dedup en dominio:** `test_dedup.py` en rojo → verde. El **advisor revisa los tests de dedup**.
6. **Repositorio:** `test_dedup_repo.py` en rojo → verde contra `pg_trgm` real.
7. **Adaptador OSM** con la fixture sintética: query, User-Agent, mapeo, descarte, truncado, limitador, costos y fallo en rojo → verde; después `test_overpass_query_escribe_fila_en_costos`. El **advisor revisa los tests de costos**.
8. **Suite de contrato** con `[osm_overpass]` + actualización de `test_registro.py`: rojo → verde.
9. **`EjecutarBusqueda` con dos fuentes:** `test_busqueda_dos_fuentes.py` y `test_contacto_no_aparece_en_logs` en rojo → verde.
10. **CLI** con el resumen por fuente y **una** corrida real contra Overpass (Bogotá, 4711), avisada antes: anotar segundos, elementos, cuántos traen teléfono, el `name` real de la relación de Bogotá y la forma de la respuesta. Si difiere de la fixture, se corrige la fixture y se vuelve al paso 7.
11. **`docs/arquitectura-backend.md`:** normalización, dedup, cifrado y cómo mapear un CIIU nuevo. Es lo primero que se recorta si el tiempo aprieta.

**Cuándo cortar:** si a las 4 h falta algo, se corta en este orden, y cada corte baja exactamente estos tests:

| Orden | Se corta | Test que se baja | Queda en su lugar |
|---|---|---|---|
| 1 | Paso 11 (doc) | — | Deuda anotada en el PR; el 013 la cierra. |
| 2 | Desglose por regla (1/2/3/4) en la CLI | ninguno (la CLI no tiene test de formato) | Resumen con fusionados en total. |
| 3 | Pares de plural en integración | `test_plural_largo_cae_en_fusion`, `test_plural_corto_cae_en_revision` | Los bordes en `test_bordes_de_similitud` (unitario). |
| 4 | Limitador con reloj falso | `test_limitador_espera_un_segundo_entre_requests` | `sleep(1)` fijo antes de cada request, con `# ponytail:`. |

**No se cortan:** la regla 4 con su chequeo de geo (sin ella, Supersociedades y OSM no se unen: ver `test_supersociedades_y_osm_dan_un_lead`, y el PRD §9 pide los 4 niveles), el veto, el cifrado, el `wa.me` y los logs.

## Riesgos
- **El nombre de la ciudad en OSM no coincide** ("Bogotá" vs "Bogotá, Distrito Capital"): la query vuelve vacía sin error. La corrida real del paso 10 lo verifica y la CLI avisa "0 elementos: revisar `--ciudad`".
- **Overpass público lento o con 429** en horas pico: hay reintento con `Retry-After` y `OVERPASS_URL` permite cambiar de instancia sin tocar código.
- **Cobertura desigual de OSM:** muchos negocios sin teléfono o sin `name`. El resumen por fuente lo muestra; no se infla.
- **Falsos positivos del dedup:** dos sucursales con el mismo teléfono o dominio quedan en un lead (decisión explícita). Los nombres parecidos de negocios distintos van a revisión, no a fusión, y ningún par se fusiona por nombre sin geo en los dos y ≤ 250 m. Los pares de los tests salen de una emulación de `pg_trgm` y se confirman en el paso 6.
- **Croma sin geo para Supersociedades:** todos los cruces por regla 4 van a revisión y la cola crece. Se ve en la corrida del paso 10; el 005 da la pantalla para resolverla.
- **`pg_trgm` no habilitado en Supabase** o fuera del `search_path` de `app_rt`: la migración fallaría al crear el índice GIN. La tarea 0a del 001 (rama `feature/001-walking-skeleton`) lo habilita desde el dashboard y lo verifica, y `roles.sql` pone el `search_path` y el `USAGE` sobre `extensions`; si falta, se habilita ahí, nunca desde la migración con otro rol.
- **Leads solo-OSM no contactables** hasta el 006 (`desconocido`). En BR/PE puede que ninguno lo sea hasta que el 006 tenga verificación para esos países; se reporta en el tablero.
- **`whatsapp_osm` puede ser el celular personal del tendero:** no hay detección automática; se acepta con confianza baja y habilita solo la llamada. El 006 y el 007 no deben asumir que la regla 3 lo filtra.
- **ODbL share-alike:** la base de leads mezcla datos ODbL. No se publica como base; si algún día se publica, va con la misma licencia y atribución.
- **Tiempo:** el cifrado (~45 min) y el chequeo de geo (~20 min) llevan el slice a ~5 h completo. Los cortes de la tabla de arriba lo devuelven a 4 h sin tocar lo que protege a los principios VI y VII.
