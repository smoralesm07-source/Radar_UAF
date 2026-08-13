(function () {
  "use strict";

  const state = { data: null, tab: "resumen" };

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
    if (n === null || n === undefined) return "—";
    return Number(n).toLocaleString("es-CL");
  }

  function kpiCard(label, value) {
    return `<div class="kpi"><div class="value">${esc(fmtNum(value))}</div><div class="label">${esc(label)}</div></div>`;
  }

  function renderKpis(d) {
    const k = d.kpis || {};
    document.getElementById("kpis").innerHTML = [
      kpiCard("Documentos", k.documents),
      kpiCard("Eventos", k.events),
      kpiCard("Entidades", k.entities),
      kpiCard("Sanciones registradas", k.sanctions),
      kpiCard("Monto sancionado conocido (UF)", k.sanctions_total_uf_known),
      kpiCard("Estadísticas", k.statistics),
      kpiCard("Alertas abiertas", k.open_watch_items),
      kpiCard("Fuentes configuradas", k.sources_configured),
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
          tipologias: "normativa", datos_abiertos: "estadisticas", calidad: "calidad", mejoras: "mejoras",
        };
        setTab(map[btn.dataset.jump] || "resumen");
      });
    });
  }

  function table(headers, rows) {
    if (!rows.length) return `<div class="empty-state">Sin registros todavía. Esta vista se completa con la próxima corrida en línea del colector.</div>`;
    const head = `<tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>`;
    const body = rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("");
    return `<div class="table-wrap"><table>${head}${body}</table></div>`;
  }

  function viewResumen(d) {
    const cov = d.coverage || {};
    const byType = (d.documents_by_type || []).map((x) => `${badge(x.name)} <span class="small muted">${x.count}</span>`).join(" ");
    return `
      <div class="panel">
        <h2>Estado general</h2>
        <p class="muted small">Generado: ${esc(d.generated_at)} · Versión ${esc(d.version)}</p>
        <h3>Documentos por tipo</h3>
        <div class="pill-row">${byType || '<span class="muted small">Sin documentos aún.</span>'}</div>
        <h3>Cobertura de fuentes</h3>
        <p class="small">${fmtNum(cov.sources && cov.sources.with_at_least_one_run)} de ${fmtNum(cov.sources && cov.sources.configured)} fuentes configuradas registran al menos una corrida.
        ${cov.sources && cov.sources.never_run && cov.sources.never_run.length ? `Pendientes de primera corrida: <span class="mono">${cov.sources.never_run.map(esc).join(", ")}</span>` : ""}</p>
      </div>
      <div class="panel">
        <h2>Eventos recientes</h2>
        ${table(["Fecha", "Tipo", "Título", "Fuente"], (d.events || []).slice(0, 25).map((e) => [
          esc(e.event_date || "—"), badge(e.event_type), esc(e.title), `<a href="${esc(e.source_url)}" target="_blank" rel="noopener">enlace</a>`,
        ]))}
      </div>`;
  }

  function viewNormativa(d) {
    const docs = (d.documents || []).filter((x) => ["CIRCULAR", "LEY", "INFORME_TIPOLOGIAS", "SEED_FACT"].includes(x.document_type));
    return `<div class="panel">
      <h2>Normativa y tipologías</h2>
      <p class="small muted">Circulares, marco legal e informes de tipologías/señales de alerta detectados. Los registros con origen "semilla OSINT" provienen de una búsqueda web verificada con fuente citada, no de scraping directo, y quedan marcados hasta ser confirmados en una corrida en línea.</p>
      ${table(["Tipo", "N°", "Título", "Fecha", "Estado", "Fuente"], docs.map((x) => [
        badge(x.document_type), esc(x.document_number || "—"), esc(x.title), esc(x.document_date || "—"),
        badge(x.status), `<a href="${esc(x.source_url)}" target="_blank" rel="noopener">enlace</a>`,
      ]))}
    </div>`;
  }

  function viewSanciones(d) {
    return `<div class="panel">
      <h2>Sanciones</h2>
      <p class="small muted">Resoluciones sancionatorias ejecutoriadas. Una sanción administrativa no equivale a una condena penal por lavado de activos ni acredita responsabilidad individual.</p>
      ${table(["Entidad", "Resolución", "Fecha", "Monto UF", "Fuente"], (d.sanctions || []).map((s) => [
        esc(s.entity_name), esc(s.resolution_number || "—"), esc(s.resolution_date || "—"),
        s.amount_uf ? fmtNum(s.amount_uf) : "—", `<a href="${esc(s.source_url)}" target="_blank" rel="noopener">enlace</a>`,
      ]))}
    </div>`;
  }

  function viewEstadisticas(d) {
    return `<div class="panel">
      <h2>Sujetos obligados y estadísticas</h2>
      ${table(["Métrica", "Categoría", "Valor", "Unidad", "Corte", "Procedencia", "Fuente"], (d.statistics || []).map((s) => [
        esc(s.metric), esc(s.category), fmtNum(s.value), esc(s.unit || "—"), esc(s.as_of_date || s.period || "—"),
        badge(s.capture_method), `<a href="${esc(s.source_url)}" target="_blank" rel="noopener">enlace</a>`,
      ]))}
    </div>
    <div class="panel">
      <h2>Entidades identificadas</h2>
      ${table(["Nombre", "Tipo", "RUT"], (d.entities || []).map((e) => [esc(e.name), badge(e.entity_type), esc(e.rut || "—")]))}
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
      <h2>Mejoras propuestas</h2>
      <p class="small muted">Backlog de mejoras priorizado a partir de la revisión de consistencia de esta primera versión del radar.</p>
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
      'Radar UAF · datos publicos derivados de <a href="https://www.uaf.cl" target="_blank" rel="noopener">uaf.cl</a> y ' +
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
