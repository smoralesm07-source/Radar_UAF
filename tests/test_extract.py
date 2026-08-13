from radar_uaf.extract import (
    first_date,
    parse_normativa_index,
    parse_registry_snapshot,
    parse_sanciones_table,
    seed_fact_to_records,
)


def test_first_date_parses_dd_mm_yyyy():
    assert first_date("Publicado el 03-04-2025 en el Diario Oficial") == "2025-04-03"


def test_first_date_returns_empty_without_match():
    assert first_date("sin fecha reconocible") == ""


def test_parse_normativa_index_extracts_circular_and_status():
    html = """
    <table>
      <tr><td>Circular UAF N°62</td><td>VIGENTE</td><td>01-06-2025</td></tr>
      <tr><td>Circular UAF N°60</td><td>DEROGADA</td><td>01-01-2020</td></tr>
    </table>
    """
    documents, watch = parse_normativa_index(html, "https://www.uaf.cl/es-cl/normativa/circulares-uaf")
    numbers = {d.document_number for d in documents}
    assert "62" in numbers and "60" in numbers
    statuses = {d.document_number: d.status for d in documents}
    assert statuses["62"] == "VIGENTE"
    assert statuses["60"] == "DEROGADA"
    assert watch == []


def test_parse_normativa_index_flags_unknown_status_as_watch():
    html = "<p>Circular UAF N°99 publicada recientemente.</p>"
    documents, watch = parse_normativa_index(html, "https://www.uaf.cl/es-cl/normativa/circulares-uaf")
    assert documents[0].status == "UNKNOWN"
    assert len(watch) == 1


def test_parse_registry_snapshot_extracts_count():
    html = "<p>El Registro cuenta con 8.970 entidades inscritas al 30-06-2025.</p>"
    stats = parse_registry_snapshot(html, "https://www.uaf.cl/es-cl/sujetos-obligados/sector-privado/inscritos-en-la-uaf")
    assert any(s.value == 8970 for s in stats)


def test_parse_sanciones_table_extracts_rows():
    html = """
    <table>
      <tr><th>Nombre</th><th>Fecha</th><th>Monto</th></tr>
      <tr><td>Empresa Ejemplo SpA</td><td>15-03-2024</td><td>120 UF</td></tr>
    </table>
    """
    sanctions = parse_sanciones_table(html, "https://www.uaf.cl/entidades_reportantes/sanciones.aspx")
    assert len(sanctions) == 1
    assert sanctions[0].entity_name == "Empresa Ejemplo SpA"
    assert sanctions[0].resolution_date == "2024-03-15"
    assert sanctions[0].amount_uf == 120.0


def test_seed_fact_to_records_marks_pending_confirmation():
    fact = {
        "fact_id": "test-fact",
        "category": "NORMATIVA",
        "title": "Hecho de prueba",
        "description": "Descripcion",
        "source_url": "https://www.uaf.cl/es-cl/normativa/circulares-uaf",
        "confidence": 0.7,
    }
    document, statistic, event = seed_fact_to_records(fact)
    assert document.status == "SEED_PENDING_LIVE_CONFIRMATION"
    assert statistic is None
    assert event.event_type == "SEED_FACT_CAPTURADO"
