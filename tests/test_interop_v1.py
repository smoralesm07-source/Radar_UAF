from radar_uaf.interop import adapt_entity_record, global_entity_id, normalize_rut


def test_valid_rut_is_global_identity():
    assert normalize_rut("96.921.130-0") == "96921130-0"
    assert global_entity_id("96.921.130-0") == "ENT-RUT-96921130-0"


def test_invalid_rut_is_never_global_identity():
    row = adapt_entity_record({"entity_id": "ENT-LOCAL-HASH", "name": "Ejemplo", "rut": "96.921.130-1"})
    assert row["entity_id"] is None
    assert row["source_entity_id"] == "ENT-LOCAL-HASH"
    assert row["candidate_entity_id"] == "ENT-LOCAL-HASH"
    assert row["identity_status"] == "UNRESOLVED"


def test_role_does_not_define_identity():
    a = adapt_entity_record({"entity_id": "LOCAL-A", "rut": "96.921.130-0"}, role="OBLIGED_ENTITY")
    b = adapt_entity_record({"entity_id": "LOCAL-B", "rut": "96.921.130-0"}, role="SANCTIONED_ENTITY")
    assert a["entity_id"] == b["entity_id"] == "ENT-RUT-96921130-0"
    assert a["entity_role"] != b["entity_role"]
