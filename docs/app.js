(function () {
  "use strict";

  const state = { data: null, tab: "resumen" };

  const METRIC_LABELS = {
    entidades_reportantes_total: "Entidades reportantes totales",
    sujetos_obligados_sector_privado: "Sujetos obligados · sector privado",
    sujetos_obligados_sector_privado_rut_unicos: "Sujetos obligados · RUT únicos",
    entidades_publicas_registradas: "Entidades públicas registradas",
    entidades_publicas_rut_unicos: "Entidades públicas · RUT únicos",
    ros_recibidos: "ROS recibidos",
    roe_recibidos: "ROE recibidos",
    roe_recibidos_miles: "ROE recibidos (miles)",
    acciones_supervision: "Acciones de supervisión",
    procesos_sancionatorios_iniciados: "Procesos sancionatorios iniciados",
    procesos_sancionatorios_finalizados: "Procesos sancionatorios finalizados",
    multas_sancionatorias_uf: "Multas sancionatorias",
    personas_informadas_en_ros: "Personas informadas en ROS",
    ros_con_indicios_laft: "ROS con indicios LA/FT",
    personas_capacitadas: "Personas capacitadas",
    dataset_recursos_publicados: "Recursos publicados en datos.gob.cl",
  };

  const CATEGORY_LABELS = {
    SUJETOS_OBLIGADOS: "Sujetos obligados",
    INTELIGENCIA_FINANCIERA: "Inteligencia financiera",
    SUPERVISION: "Supervisión",
    SANCIONES: "Sanciones",
    CAPACITACION: "Capacitación",
    DATOS_ABIERTOS: "Datos abiertos",
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function badge(text) {
    const cls = String(text || "UNKNOWN").replace(/[^A-Za-z0-9_]/g, "_");
    return `<span class="badge ${esc(cls)}">${esc(text || "—")}</span>`;
  }

  function fmtNum(n) {
    if (n === null || n === undefined || n === "") return "—";
    const numeric = Number(n);
    if (!Number.isFinite(numeric)) return String(n);
    return numeric.toLocaleString("es-CL", { maximumFractionDigits: 2 });
  }

  function fmtDate(value) {
    if (!value) return "—";
    const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : esc(value);
  }

  function metricLabel(metric) {
    return METRIC_LABELS[metric] || String(metric || "—").replaceAll("_", " ");
  }

  function categoryLabel(category) {
    return CATEGORY_LABELS[category] || String(category || "—").replaceAll("_", " ");
  }

  function kpiCard(label, value, meta) {
    return `<div class="kpi"><div class="value">${esc(fmtNum(value))}</div><div class="label">${esc(label)}</div>${meta ? `<div class="kpi-meta">${esc(meta)}</div>` : ""}</div>`;
  }

  function renderKpis(d) {
    const k = d.kpis || {};
    document.getElementById("kpis").innerHTML = [
      kpiCard("Sujetos obligados privados", k.registered_private_latest, k.registered_private_as_of ? `corte ${fmtDate(k.registered_private_as_of)}` : ""),
      kpiCard("Registro total UAF", k.registered_total_latest, k.registered_total_as_of ? `corte ${fmtDate(k.registered_total_as_of)}` : ""),
      kpiCard("ROS recibidos", k.ros_latest, k.ros_latest_as_of ? `año ${String(k.ros_latest_as_of).slice(0, 4)}` : ""),
      kpiCard("ROE recibidos", k.roe_latest, k.roe_latest_as_of ? `año ${String(k.roe_latest_as_of).slice(0, 4)}` : ""),
      kpiCard("Acciones de supervisión", k.supervision_latest, k.supervision_latest_as_of ? `año ${String(k.supervision_latest_as_of).slice(0, 4)}` : ""),
      kpiCard("Multas sancionatorias (UF)", k.fines_uf_latest, k.fines_uf_latest_as_of ? `año ${String(k.fines_uf_latest_as_of).slice(0, 4)}` : ""),
      kpiCard("Entidades estructuradas", k.entities, "RUT / nombre / actividad"),
      kpiCard("Calidad", k.quality_status, `${fmtNum(k.sources_configured)} fuentes configuradas`),
    ].join("");
  }

  function renderQuestions(d) {
    const box = document.getElementById("questions");
    box.innerHTML = (d.question_catalog || [])
      .map((q) => `<button data-jump="${esc(q.id)}">${esc(q.label)}</button>`)
      .join("");
    box.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const map = {
          sanciones: "sanciones", normativa: "normativa", sujetos_obligados: "estadisticas",
          estadisticas: "estadisticas", calidad: "calidad", mejoras: "mejoras",
        };
        setTab(map[btn.dataset.jump] || "resumen");
      });
    });
  }

  function table(headers, rows) {
    if (!rows.length) return `<div class="empty-state">Sin registros disponibles para esta vista.</div>`;
    const head = `<tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>`;
    const body = rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("");
    return `<div class="table-wrap"><table>${head}${body}</table></div>`;
  }

  function viewResumen(d) {
    const cov = d.coverage || {};
    const k = d.kpis || {};
    const byType = (d.documents_by_type || []).map((x) => `${badge(x.name)} <span class="small muted">${x.count}</span>`).join(" ");
    return `
      <div class="panel summary-callout">
        <div>
          <div class="section-kicker">Registro vigente</div>
          <h2>${fmtNum(k.registered_private_latest)} sujetos obligados del sector privado</h2>
          <p class="muted">Fuente: último registro UAF procesado desde el XLSX oficial · corte ${fmtDate(k.registered_private_as_of)}. El radar conserva por separado las series estadísticas anuales para no mezclar fechas de referencia.</p>
        </div>
        <button class="text-action" data-open-stats>Ver estadísticas →</button>
      </div>
      <div class="panel">
        <h2>Estado general</h2>
        <p class="muted small">Generado: ${esc(d.generated_at)} · Versión ${esc(d.version)}</p>
        <h3>Documentos por tipo</h3>
        <div class="pill-row">${byType || '<span class="muted small">Sin documentos aún.</span>'}</div>
        <h3>Cobertura de fuentes</h3>
        <p class="small">${fmtNum(cov.sources && cov.sources.with_at_least_one_run)} de ${fmtNum(cov.sources && cov.sources.configured)} fuentes configuradas registran al menos una corrida.</p>
      </div>
      <div class="panel">
        <h2>Eventos recientes</h2>
        ${table(["Fecha", "Tipo", "Título", "Fuente"], (d.events || []).slice(0, 20).map((e) => [
          esc(e.event_date || "—"), badge(e.event_type), esc(e.title), `<a href="${esc(e.source_url)}" target="_blank" rel="noopener">abrir</a>`,
        ]))}
      </div>`;
  }

  function viewNormativa(d) {
    const docs = (d.documents || []).filter((x) => ["CIRCULAR", "LEY", "INFORME_TIPOLOGIAS", "INFORME_ESTADISTICO", "SEED_FACT"].includes(x.document_type));
    return `<div class="panel">
      <h2>Normativa, tipologías e informes</h2>
      <p class="small muted">Documentos institucionales detectados y trazables a su fuente oficial.</p>
      ${table(["Tipo", "N°", "Título", "Fecha", "Estado", "Fuente"], docs.map((x) => [
        badge(x.document_type), esc(x.document_number || "—"), esc(x.title), esc(x.document_date || "—"),
        badge(x.status), `<a href="${esc(x.source_url)}" target="_blank" rel="noopener">abrir</a>`,
      ]))}
    </div>`;
  }

  function viewSanciones(d) {
    return `<div class="panel">
      <h2>Sanciones</h2>
      <p class="small muted">Resoluciones sancionatorias ejecutoriadas. Una sanción administrativa no equivale a una condena penal por lavado de activos ni acredita responsabilidad individual.</p>
      ${table(["Entidad", "Resolución", "Fecha", "Monto UF", "Fuente"], (d.sanctions || []).map((s) => [
        esc(s.entity_name), esc(s.resolution_number || "—"), esc(s.resolution_date || "—"),
        s.amount_uf ? fmtNum(s.amount_uf) : "—", `<a href="${esc(s.source_url)}" target="_blank" rel="noopener">abrir</a>`,
      ]))}
    </div>`;
  }

  function latestCards(d) {
    const latest = d.statistics_latest || {};
    const wanted = [
      "sujetos_obligados_sector_privado", "entidades_publicas_registradas", "entidades_reportantes_total",
      "ros_recibidos", "roe_recibidos", "acciones_supervision", "procesos_sancionatorios_finalizados",
      "multas_sancionatorias_uf", "personas_informadas_en_ros", "ros_con_indicios_laft",
    ];
    return wanted.filter((m) => latest[m]).map((m) => {
      const s = latest[m];
      return `<div class="stat-card">
        <div class="stat-label">${esc(metricLabel(m))}</div>
        <div class="stat-value">${fmtNum(s.value)} <span>${esc(s.unit || "")}</span></div>
        <div class="stat-meta">${fmtDate(s.as_of_date || s.period)} · ${badge(s.capture_method)}</div>
        <a href="${esc(s.source_url)}" target="_blank" rel="noopener">Fuente oficial</a>
      </div>`;
    }).join("");
  }

  function seriesCards(d) {
    const priority = [
      "entidades_reportantes_total", "ros_recibidos", "roe_recibidos_miles", "acciones_supervision",
      "procesos_sancionatorios_iniciados",
    ];
    const series = (d.statistics_series || []).filter((s) => priority.includes(s.metric));
    series.sort((a, b) => priority.indexOf(a.metric) - priority.indexOf(b.metric));
    return series.map((s) => {
      const points = s.points || [];
      return `<div class="series-card">
        <div class="series-head"><div><div class="section-kicker">${esc(categoryLabel(s.category))}</div><h3>${esc(metricLabel(s.metric))}</h3></div><span class="muted small">${esc(s.unit || "")}</span></div>
        ${table(["Período", "Valor", "Fuente"], points.map((p) => [
          esc(p.period), `<strong>${fmtNum(p.value)}</strong>`, `<a href="${esc(p.source_url)}" target="_blank" rel="noopener">UAF</a>`,
        ]))}
      </div>`;
    }).join("");
  }

  function viewEstadisticas(d) {
    const k = d.kpis || {};
    const currentRegistry = (d.statistics || []).filter((s) => s.capture_method === "UAF_REGISTRY_XLSX");
    return `
      <div class="panel">
        <div class="section-kicker">Corte vigente</div>
        <h2>Registro de sujetos obligados</h2>
        <p class="muted">El dato vigente se obtiene del archivo Excel publicado por la UAF; ya no se toma desde una cifra semilla. Sector privado: <strong>${fmtNum(k.registered_private_latest)}</strong> al ${fmtDate(k.registered_private_as_of)}. Sector público: <strong>${fmtNum(k.registered_public_latest)}</strong> al ${fmtDate(k.registered_public_as_of)}.</p>
        ${table(["Métrica", "Valor", "Unidad", "Corte", "Fuente"], currentRegistry.map((s) => [
          esc(metricLabel(s.metric)), `<strong>${fmtNum(s.value)}</strong>`, esc(s.unit || "—"), fmtDate(s.as_of_date), `<a href="${esc(s.source_url)}" target="_blank" rel="noopener">XLSX UAF</a>`,
        ]))}
      </div>
      <div class="panel">
        <div class="section-kicker">Último dato disponible por indicador</div>
        <h2>Indicadores UAF</h2>
        <div class="stats-grid">${latestCards(d)}</div>
      </div>
      <div class="panel">
        <div class="section-kicker">Informe Estadístico 2025</div>
        <h2>Series oficiales 2021–2025</h2>
        <p class="small muted">Series estructuradas desde el Informe Estadístico UAF 2025. La corrida en línea valida el último año directamente contra el PDF oficial.</p>
        <div class="series-grid">${seriesCards(d)}</div>
      </div>
      <div class="panel">
        <h2>Todas las observaciones estadísticas</h2>
        ${table(["Métrica", "Categoría", "Valor", "Unidad", "Corte", "Procedencia", "Fuente"], (d.statistics || []).map((s) => [
          esc(metricLabel(s.metric)), esc(categoryLabel(s.category)), fmtNum(s.value), esc(s.unit || "—"), fmtDate(s.as_of_date || s.period),
          badge(s.capture_method), `<a href="${esc(s.source_url)}" target="_blank" rel="noopener">abrir</a>`,
        ]))}
      </div>
      <div class="panel">
        <h2>Entidades del registro</h2>
        <p class="small muted">Muestra del registro estructurado. El dataset completo se conserva en las capas silver/gold del repositorio.</p>
        ${table(["Nombre", "Sector", "Actividad", "RUT"], (d.entities || []).map((e) => [esc(e.name), badge(e.sector || e.entity_type), esc(e.activity || "—"), esc(e.rut || "—")]))}
      </div>`;
  }

  function viewFuentes(d) {
    const cov = d.coverage || {};
    const latest = (cov.sources && cov.sources.latest_run_by_source) || {};
    const rows = Object.entries(latest).map(([id, r]) => [esc(id), badge(r.status), esc(r.finished_at || "—"), fmtNum(r.items_found), esc(r.error || "—")]);
    return `<div class="panel">
      <h2>Fuentes y corridas</h2>
      <p class="small muted">${esc(cov.warning || "")}</p>
      ${table(["Fuente", "Estado", "Última corrida", "Ítems", "Error"], rows)}
    </div>`;
  }

  function checkRow(c) {
    return `<tr><td>${esc(c.label)}</td><td>${badge(c.severity)}</td><td>${fmtNum(c.count)}</td></tr>`;
  }

  function viewCalidad(d) {
    const q = d.quality || {};
    const mix = (q.capture_method_mix || []).map((x) => `${badge(x.name)} <span class="small muted">${x.count}</span>`).join(" ");
    return `<div class="panel">
      <h2>Evaluación de consistencia <span style="margin-left:8px">${badge(q.overall_status)}</span></h2>
      <p class="small muted">Generado: ${esc(q.generated_at)}</p>
      <h3>Chequeos automáticos</h3>
      <div class="table-wrap"><table><tr><th>Chequeo</th><th>Severidad</th><th>Casos</th></tr>${(q.checks || []).map(checkRow).join("")}</table></div>
      <h3>Procedencia de las estadísticas</h3>
      <div class="pill-row">${mix || '<span class="muted small">Sin estadísticas aún.</span>'}</div>
    </div>`;
  }

  function viewMejoras(d) {
    const items = d.improvement_backlog || [];
    return `<div class="panel">
      <h2>Hoja de ruta</h2>
      <p class="small muted">Mejoras priorizadas después de incorporar registro vigente y estadísticas oficiales en v0.2.</p>
      ${items.map((it) => `
        <div class="backlog-item">
          <div class="meta">${badge(it.priority)} <span class="badge">${esc(it.area)}</span></div>
          <div class="title">${esc(it.title)}</div>
          <div class="detail">${esc(it.detail)}</div>
        </div>`).join("")}
    </div>`;
  }

  const VIEWS = {
    resumen: viewResumen, normativa: viewNormativa, sanciones: viewSanciones,
    estadisticas: viewEstadisticas, fuentes: viewFuentes, calidad: viewCalidad, mejoras: viewMejoras,
  };

  function setTab(tab) {
    state.tab = tab;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    document.getElementById("view").innerHTML = VIEWS[tab] ? VIEWS[tab](state.data) : "";
    document.querySelectorAll("[data-open-stats]").forEach((btn) => btn.addEventListener("click", () => setTab("estadisticas")));
  }

  function init(data) {
    state.data = data;
    document.getElementById("generated").textContent = `Última actualización: ${data.generated_at || "—"}`;
    document.getElementById("disclaimer").textContent = data.disclaimer || "";
    renderKpis(data);
    renderQuestions(data);
    document.querySelectorAll("#tabs button").forEach((btn) => btn.addEventListener("click", () => setTab(btn.dataset.tab)));
    setTab("resumen");
    document.getElementById("footer").innerHTML =
      'Radar UAF v0.2 · fuentes oficiales <a href="https://www.uaf.cl" target="_blank" rel="noopener">uaf.cl</a> y ' +
      '<a href="https://datos.gob.cl/organization/unidad_de_analisis_financiero" target="_blank" rel="noopener">datos.gob.cl</a> · ' +
      '<a href="https://github.com/smoralesm07-source/Radar_UAF" target="_blank" rel="noopener">código fuente</a>';
  }

  fetch("data/dashboard.json", { cache: "no-store" })
    .then((r) => r.json())
    .then(init)
    .catch((err) => {
      document.getElementById("view").innerHTML = `<div class="panel"><p>No fue posible cargar los datos: ${esc(err)}</p></div>`;
    });
})();
