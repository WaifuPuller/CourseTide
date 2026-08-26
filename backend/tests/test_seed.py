from backend.scripts.validate_seed import validate_seed_data


def test_seed_data_validation():
    """Verify that seed files in /data strictly match VALIDATION_REPORT.json."""
    assert validate_seed_data() is True
