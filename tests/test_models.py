from radar_uaf.models import Document, stable_id


def test_stable_id_is_deterministic():
    a = stable_id("DOC", "CIRCULAR", "62")
    b = stable_id("DOC", "circular", " 62 ")
    assert a == b
    assert a.startswith("DOC-")


def test_stable_id_changes_with_parts():
    a = stable_id("DOC", "CIRCULAR", "62")
    b = stable_id("DOC", "CIRCULAR", "60")
    assert a != b


def test_document_to_dict_roundtrip():
    doc = Document(
        document_id="DOC-1",
        source_system="UAF",
        source_module="NORMATIVA",
        source_url="https://www.uaf.cl/es-cl/normativa/circulares-uaf",
        title="Circular UAF N°62",
    )
    data = doc.to_dict()
    assert data["document_id"] == "DOC-1"
    assert data["source_url"].startswith("https://www.uaf.cl")
