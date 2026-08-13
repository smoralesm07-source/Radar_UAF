# Radar UAF

Radar OSINT para transformar información pública de la **Unidad de Análisis Financiero de Chile (UAF)** —y del Portal de Datos Abiertos del Estado (`datos.gob.cl`)— en datos estructurados, trazables y reutilizables para inteligencia de riesgo con enfoque **AML/LA-FT** (lavado de activos y financiamiento del terrorismo).

> Una sanción administrativa, una cifra agregada o una coincidencia con una lista no acredita por sí sola lavado de activos, financiamiento del terrorismo, dolo ni responsabilidad individual. El sistema prioriza revisión analítica y conserva siempre la evidencia y URL oficial de origen.

## Por qué existe y cómo se relaciona con otros radares

Este proyecto replica deliberadamente la **arquitectura y metodología de [Radar-CGR](https://github.com/smoralesm07-source/Radar-CGR)** (Contraloría General de la República): capas bronze/silver/gold, colectores desacoplados de la lógica de negocio, tablas semánticas con `upsert` idempotente, ejecución sin servidor vía GitHub Actions + GitHub Pages, y un dashboard estático que lee un único `docs/data/dashboard.json`.

La intención declarada es poder **conectar Radar UAF con otros radares del mismo autor** (Radar-CGR, Radar-SII, Radar-Sectorial) sobre un Entity Hub común. Por eso el modelo `Entity` de este repositorio usa exactamente la misma forma (`entity_id`, `entity_type`, `name`, `normalized_name`, `rut`) que Radar-CGR — ver el backlog de mejoras para el trabajo pendiente de unificación real de identificadores entre repositorios.

## Alcance de datos

| Dominio | Fuente | Colector |
|---|---|---|
| Marco legal (Ley 19.913) | `uaf.cl/es-cl/normativa/nuestra-ley` | `page_discovery` |
| Circulares (vigentes/derogadas) | `uaf.cl/es-cl/normativa/circulares-uaf` | `normativa_index` |
| Sujetos obligados (registro) | `uaf.cl/es-cl/sujetos-obligados/...` | `page_discovery` / `registry_snapshot` |
| Listas de Resoluciones ONU | `uaf.cl/.../listas-de-resoluciones-onu` | `sanctions_list` |
| Sanciones ejecutoriadas | rutas legadas `.aspx` (ver nota abajo) | `sanciones_legacy` |
| Noticias / comunicados | `uaf.cl/es-cl/` | `news_index` |
| Datasets abiertos (ROS, comiso, procesos judiciales) | API CKAN de `datos.gob.cl` | `ckan_datasets` |

El detalle completo de fuentes vive en [`config/sources.json`](config/sources.json).

## Modelo de datos

```text
SOURCE
  |
  +--> DOCUMENT (LEY | CIRCULAR | INFORME_TIPOLOGIAS | NOTICIA | DATASET | SEED_FACT)
  |        |
  |      EVENT (NORMATIVA_PUBLICADA | SANCION_EJECUTORIADA | NOTICIA | DATASET_ACTUALIZADO)
  |
  +--> SANCTION ---> ENTITY (SANCIONADO_ORGANIZACION | SANCIONADO_PERSONA)
  |
  +--> STATISTIC (metric, category, value, capture_method)
  |
  +--> WATCH_ITEM (NORMATIVA_CAMBIO | SANCION_NUEVA | DATASET_CAMBIO)
  |
  +--> SOURCE_RUN
```

Tablas primarias: `documents`, `events`, `entities`, `sanctions`, `statistics`, `watch_items`, `source_runs` (JSONL en `data/silver/`, exportadas a Parquet en `data/gold/`). Esquemas formales en [`schemas/`](schemas).

### Procedencia de los datos (`capture_method` / `status`)

Cada estadística y documento declara explícitamente cómo se obtuvo:

- `LIVE_SCRAPE`: extraído directamente del HTML de `uaf.cl` en una corrida del colector.
- `CKAN_API`: obtenido de la API estructurada de `datos.gob.cl`.
- `SEED_OSINT_SUMMARY` / `SEED_PENDING_LIVE_CONFIRMATION`: hecho público verificado manualmente vía búsqueda web con fuente citada (ver [`config/seed_facts.json`](config/seed_facts.json)), usado para poblar la primera versión del radar mientras el colector corre por primera vez con acceso real a internet. **No se fabricó ningún dato de sanciones individuales**: los hechos semilla son únicamente cifras agregadas y hitos institucionales con URL de origen.

Esta distinción es intencional y es la base de la evaluación de consistencia: permite saber, en todo momento, qué porcentaje del dashboard es evidencia directa vs. resumen verificado pendiente de confirmación automatizada.

## Por qué el entorno de desarrollo no pudo scrapear `uaf.cl` en vivo

El proxy de red de este entorno de desarrollo bloquea el egreso hacia `www.uaf.cl` (`EGRESS_BLOCKED`). Por eso esta primera versión se construyó y validó con `python run.py --skip-network`, usando los hechos semilla citados arriba para no dejar el dashboard vacío. El colector en vivo (`collectors.py`, `extract.py`) sí quedó implementado y se ejecutará con acceso real a internet **la primera vez que corra en GitHub Actions** (`.github/workflows/radar.yml`), que no tiene esa restricción de red.

## Ejecución

```bash
pip install -r requirements.txt
pytest -q                    # 17 pruebas, sin red
python run.py --skip-network # recalcula silver/gold/dashboard desde lo ya persistido + semillas
python run.py                # corrida completa con red (colector en vivo)
```

El pipeline es idempotente: `upsert_jsonl` compara contenido semántico (ignorando `retrieved_at`/`last_seen`) para no marcar como "actualizado" un registro sin cambios reales.

## Dashboard

`docs/index.html` es un sitio estático (sin build step) que consume `docs/data/dashboard.json`. Pestañas: **Resumen, Normativa, Sanciones, Sujetos obligados & estadísticas, Fuentes, Calidad de datos, Mejoras propuestas**. Se publica automáticamente en GitHub Pages vía `.github/workflows/pages.yml` tras cada corrida exitosa del colector.

## Evaluación de consistencia (estado inicial)

Ejecutando `evaluate_consistency()` sobre la primera carga (8 hechos semilla, 0 corridas en vivo aún):

- **OK** — sin duplicados de entidades, sin sanciones sin monto, sin normativa con vigencia ambigua (no hay aún filas suficientes para que estos chequeos tengan señal real).
- **LOW** — 5 de 8 documentos semilla no traen fecha exacta reconocible (son hitos descriptivos, no publicaciones puntuales); es esperable y no bloquea el uso del radar.
- El mix de `capture_method` es 100% `SEED_OSINT_SUMMARY`: **es la limitación más importante de esta entrega** y se resuelve automáticamente en cuanto el colector corra con red real.

## Mejoras propuestas (backlog priorizado)

El mismo contenido, en detalle y por prioridad, se sirve en la pestaña **Mejoras propuestas** del dashboard (`radar_uaf/dashboard.py::IMPROVEMENT_BACKLOG`). Resumen:

1. **[Alta] Confirmar rutas de sanciones** — las URLs `.aspx` legadas pueden haber sido reemplazadas por una ruta `/es-cl/` no identificada aún; validar en la primera corrida real.
2. **[Alta] Sanciones fila por fila** — hoy solo hay cifras agregadas (2.915 UF / 63 entidades en 2024); falta extraer resoluciones individuales con RUT, artículo infringido y monto.
3. **[Alta] Series temporales CKAN** — descargar los recursos (CSV/XLSX) de los datasets de `datos.gob.cl`, no solo su metadata.
4. **[Alta] Entity Hub compartido** — acordar un `entity_id` verdaderamente común entre Radar-UAF, Radar-CGR, Radar-SII y Radar-Sectorial (candidato natural: RUT normalizado).
5. **[Media] Diff de Listas ONU** — versionar altas/bajas en vez de solo registrar la página como documento de referencia.
6. **[Media] Validación de dígito verificador de RUT**.
7. **[Media] Trazabilidad circular-reemplaza-a-circular** (la N°62 declara qué circulares deroga).
8. **[Media] Auditoría de `robots.txt`** y throttling explícito por dominio.
9. **[Baja] Validación de esquema JSON en CI** sobre una muestra de `silver/*.jsonl`.
10. **[Baja] Backfill histórico** de ediciones previas del Informe de Tipologías.

## Próximas extensiones

- Publicación semestral del Registro de Entidades Reportantes como serie temporal (enero/julio).
- Vinculación cruzada sanciones UAF ↔ hallazgos Radar-CGR sobre el mismo RUT/organismo.
- Alertas automáticas (`WatchItem`) cuando una circular cambia de estado o se publica una nueva edición del Informe de Tipologías.
