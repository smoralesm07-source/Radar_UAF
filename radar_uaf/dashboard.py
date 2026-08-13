from __future__ import annotations

import json
from collections import Counter

from .config import DOCS_DIR
from .coverage import summarize_coverage
from .quality import evaluate_consistency
from .storage import read_jsonl, table_path

DISCLAIMER = (
    "Radar UAF transforma informacion publicada por la Unidad de Analisis Financiero de Chile "
    "y por el Portal de Datos Abiertos en datos estructurados para priorizacion analitica AML/LA-FT. "
    "Una sancion, una cifra agregada o una coincidencia con una lista no acredita por si sola lavado "
    "de activos, financiamiento del terrorismo, dolo ni responsabilidad individual. Los hechos marcados "
    "como 'semilla OSINT' provienen de busqueda web verificada con fuente citada, no de scraping directo, "
    "y deben confirmarse en la proxima corrida en linea del colector antes de tratarse como definitivos."
)

IMPROVEMENT_BACKLOG = [
    {
        "id": "confirm-legacy-sanciones-path",
        "area": "Cobertura",
        "priority": "ALTA",
        "title": "Confirmar si las rutas .aspx de sanciones siguen sirviendo el listado completo",
        "detail": "El sitio migro a una CMS bajo /es-cl/, pero las rutas legadas /entidades_reportantes/sanciones.aspx y /lavado/sanciones.aspx siguen indexadas. Es necesario validar en la primera corrida en GitHub Actions si responden 200, si redirigen, o si el listado historico completo ahora vive en una ruta /es-cl/ aun no identificada, y ajustar config/sources.json en consecuencia.",
    },
    {
        "id": "individual-sanction-records",
        "area": "Extraccion",
        "priority": "ALTA",
        "title": "Extraer resoluciones sancionatorias individuales, no solo cifras agregadas",
        "detail": "Los hechos semilla actuales solo incluyen totales anuales (2.915 UF / 63 entidades en 2024) tomados de cobertura de prensa. El colector en vivo debe parsear la tabla oficial fila por fila (numero de resolucion, RUT, fecha, monto UF, articulo infringido) para permitir analisis de recurrencia por entidad.",
    },
    {
        "id": "ckan-time-series",
        "area": "Datos abiertos",
        "priority": "ALTA",
        "title": "Convertir los datasets CKAN de datos.gob.cl en series temporales reales",
        "detail": "datos.gob.cl publica ROS enviadas al Ministerio Publico, ROS recibidas, penas de comiso y procesos judiciales por LA. Hoy solo se registra metadata del dataset (recursos, fecha de modificacion); falta descargar los recursos CSV/XLSX y modelarlos como observaciones anuales/mensuales en la tabla statistics.",
    },
    {
        "id": "entity-hub-crosslink",
        "area": "Arquitectura",
        "priority": "ALTA",
        "title": "Definir el Entity Hub compartido con Radar-CGR, Radar-SII y Radar-Sectorial",
        "detail": "El modelo Entity de este repositorio ya replica la forma (entity_id, entity_type, name, normalized_name, rut) usada en Radar-CGR para facilitar un cruce futuro. Falta acordar un esquema de entity_id verdaderamente compartido (idealmente anclado en RUT normalizado) y un mecanismo de sincronizacion entre repositorios, por ejemplo un dataset comun publicado por cada radar y consumido por los demas.",
    },
    {
        "id": "onu-list-diffing",
        "area": "Sanciones internacionales",
        "priority": "MEDIA",
        "title": "Versionar las Listas de Resoluciones ONU para detectar altas y bajas",
        "detail": "La pagina de Listas de Resoluciones ONU cambia con cada actualizacion del Consejo de Seguridad. Se debe capturar snapshot completo, calcular diff contra la corrida anterior y generar WatchItem por cada persona/entidad agregada o retirada, en vez de solo registrar la pagina como documento.",
    },
    {
        "id": "rut-validation",
        "area": "Calidad de datos",
        "priority": "MEDIA",
        "title": "Validar digito verificador de RUT antes de aceptar una entidad",
        "detail": "parse_rut() hoy solo reconoce el patron NN.NNN.NNN-D por regex. Se recomienda anadir validacion de digito verificador (modulo 11) para reducir falsos positivos al extraer RUT de texto libre de noticias o resoluciones.",
    },
    {
        "id": "circular-diff-text",
        "area": "Normativa",
        "priority": "MEDIA",
        "title": "Diferenciar contenido normativo, no solo numero y estado",
        "detail": "Hoy una Circular se registra con numero, fecha y estado (vigente/derogada). Un analisis regulatorio mas util requeriria extraer las 55 actividades economicas obligadas mencionadas y marcar que circular fue derogada por cual, replicando la trazabilidad que la propia Circular N°62 declara sobre las circulares que reemplaza.",
    },
    {
        "id": "robots-and-rate-limit-audit",
        "area": "Cumplimiento tecnico",
        "priority": "MEDIA",
        "title": "Auditar robots.txt y agregar throttling explicito por dominio",
        "detail": "El HTTPClient reutiliza el patron de reintentos de Radar-CGR pero aun no valida robots.txt de uaf.cl ni de datos.gob.cl antes de la primera corrida real. Conviene automatizar esa verificacion en CI y registrar el resultado en source_runs.",
    },
    {
        "id": "ci-schema-validation",
        "area": "Ingenieria de datos",
        "priority": "BAJA",
        "title": "Validar cada fila contra su JSON Schema en CI",
        "detail": "Los esquemas en schemas/*.json existen mas como documentacion que como gate ejecutable. Anadir un test que valide una muestra de silver/*.jsonl contra su schema en cada corrida de pytest.",
    },
    {
        "id": "historical-backfill",
        "area": "Cobertura",
        "priority": "BAJA",
        "title": "Backfill historico de Informes de Tipologias anteriores a la decima edicion",
        "detail": "Solo se referencia la decima edicion (2019-2023). La UAF ha publicado ediciones previas; incorporarlas permitiria una serie temporal comparable de tipologias/senales de alerta ano contra ano, similar al enfoque de barrido historico que Radar-CGR aplica sobre auditorias.",
    },
]

QUESTION_CATALOG = [
    {"id": "sanciones", "label": "Que entidades y montos concentran las sanciones UAF?"},
    {"id": "normativa", "label": "Que circulares estan vigentes y cuales fueron derogadas?"},
    {"id": "sujetos_obligados", "label": "Cuantos sujetos obligados hay inscritos y como evoluciona el registro?"},
    {"id": "tipologias", "label": "Que tipologias y senales de alerta identifica la UAF?"},
    {"id": "datos_abiertos", "label": "Que series estadisticas publica la UAF en datos.gob.cl?"},
    {"id": "calidad", "label": "Que tan consistentes y verificados estan los datos del radar?"},
    {"id": "mejoras", "label": "Que mejoras estan priorizadas para las proximas corridas?"},
]


def build_dashboard() -> dict:
    documents = read_jsonl(table_path("documents"))
    events = read_jsonl(table_path("events"))
    entities = read_jsonl(table_path("entities"))
    sanctions = read_jsonl(table_path("sanctions"))
    statistics = read_jsonl(table_path("statistics"))
    watch_items = read_jsonl(table_path("watch_items"))
    source_runs = read_jsonl(table_path("source_runs"))

    coverage = summarize_coverage()
    quality = evaluate_consistency()

    document_type_counts = Counter(d.get("document_type", "UNKNOWN") for d in documents)
    sanction_amounts = [s.get("amount_uf") for s in sanctions if s.get("amount_uf")]

    kpis = {
        "documents": len(documents),
        "events": len(events),
        "entities": len(entities),
        "sanctions": len(sanctions),
        "sanctions_total_uf_known": round(sum(sanction_amounts), 1) if sanction_amounts else 0,
        "statistics": len(statistics),
        "open_watch_items": sum(1 for w in watch_items if w.get("status") == "OPEN"),
        "seed_facts_pending_confirmation": sum(1 for d in documents if d.get("status") == "SEED_PENDING_LIVE_CONFIRMATION"),
        "sources_configured": coverage["sources"]["configured"],
        "sources_never_run": len(coverage["sources"]["never_run"]),
        "quality_status": quality["overall_status"],
    }

    payload = {
        "version": "0.1.0",
        "generated_at": coverage["generated_at"],
        "disclaimer": DISCLAIMER,
        "kpis": kpis,
        "documents": sorted(documents, key=lambda x: x.get("document_date", "") or "", reverse=True)[:400],
        "documents_by_type": [{"name": k, "count": v} for k, v in document_type_counts.most_common()],
        "events": sorted(events, key=lambda x: x.get("event_date", "") or "", reverse=True)[:400],
        "entities": entities[:400],
        "sanctions": sorted(sanctions, key=lambda x: x.get("resolution_date", "") or "", reverse=True)[:400],
        "statistics": statistics[:400],
        "watch_items": sorted(watch_items, key=lambda x: (x.get("status") == "OPEN", x.get("last_seen", "") or ""), reverse=True)[:200],
        "source_runs": sorted(source_runs, key=lambda x: x.get("finished_at", "") or "", reverse=True)[:200],
        "coverage": coverage,
        "quality": quality,
        "improvement_backlog": IMPROVEMENT_BACKLOG,
        "question_catalog": QUESTION_CATALOG,
    }

    out = DOCS_DIR / "data" / "dashboard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
