from radar_uaf.collectors import _cutoff_from_registry_page, discover_downloads
from radar_uaf.extract import parse_statistical_report, registry_result_to_records


def test_registry_cutoff_uses_latest_published_date():
    html = """
    <html><body>
      <p>Lista sujetos obligados inscritos en la UAF al 31/12/2025</p>
      <p>Lista sujetos obligados inscritos en la UAF al 30/06/2026</p>
    </body></html>
    """
    assert _cutoff_from_registry_page(html) == "2026-06-30"


def test_registry_records_keep_listed_and_unique_counts_separate():
    result = {
        "sector": "private",
        "as_of_date": "2026-06-30",
        "download_url": "https://www.uaf.cl/media/documentos/registro.xlsx",
        "listed_count": 100,
        "unique_rut_count": 97,
        "content_hash": "abc",
        "rows": [
            {"rut": "76123456-7", "name": "Empresa Uno SPA", "activity": "Factoring"},
            {"rut": "76543210-K", "name": "Empresa Dos LTDA", "activity": "Corredor de propiedades"},
        ],
    }
    documents, entities, statistics = registry_result_to_records(result)
    assert documents[0].document_type == "REGISTRO_UAF_XLSX"
    assert len(entities) == 2
    metrics = {s.metric: s.value for s in statistics}
    assert metrics["sujetos_obligados_sector_privado"] == 100
    assert metrics["sujetos_obligados_sector_privado_rut_unicos"] == 97
    assert statistics[0].as_of_date == "2026-06-30"


def test_statistical_report_extracts_2025_key_metrics():
    report = {
        "report_year": 2025,
        "report_url": "https://www.uaf.cl/media/documentos/Informe_Estadistico_2025.pdf",
        "content_hash": "abc",
        "text_excerpt": "Informe Estadístico 2025",
    }
    text = """
    Al 31 de diciembre de 2025, 9.911 personas naturales y jurídicas se encuentran inscritas.
    De estas, 9.403 pertenecen a las 55 actividades económicas y 508 son entidades públicas.
    Durante el año 2025 la UAF recibió un total de 21.828 ROS.
    Durante el 2025, la UAF recibió 1.620.219 ROE.
    En 2025, la UAF realizó 172 acciones de supervisión.
    Durante el 2025 la UAF finalizó un total de 59 procesos sancionatorios.
    Las multas a beneficio fiscal ascendieron a UF 1.925.
    Los ROS recibidos en 2025 incluyeron información de 22.348 personas.
    información de 1.132 ROS, cuyos respectivos Informes de Inteligencia fueron enviados.
    """
    documents, statistics = parse_statistical_report(report, text)
    assert documents[0].document_type == "INFORME_ESTADISTICO"
    values = {s.metric: s.value for s in statistics}
    assert values["entidades_reportantes_total"] == 9911
    assert values["sujetos_obligados_sector_privado"] == 9403
    assert values["entidades_publicas_registradas"] == 508
    assert values["ros_recibidos"] == 21828
    assert values["roe_recibidos"] == 1620219
    assert values["acciones_supervision"] == 172
    assert values["procesos_sancionatorios_finalizados"] == 59
    assert values["multas_sancionatorias_uf"] == 1925


def test_discover_downloads_keeps_official_xlsx():
    html = '<a href="/media/documentos/registro.xlsx">Buscador de sujetos obligados inscritos</a>'
    downloads = discover_downloads(html, "https://www.uaf.cl/es-cl/sujetos-obligados")
    assert downloads[0]["url"] == "https://www.uaf.cl/media/documentos/registro.xlsx"
