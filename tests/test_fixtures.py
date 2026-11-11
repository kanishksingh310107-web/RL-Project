"""Unit tests verifying test fixture schema compatibility."""
import json
from pathlib import Path
from app.core.schemas import Place, Provenance

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_synthetic_fixtures_load_and_validate():
    fixtures = list(FIXTURES_DIR.glob("*_synthetic.json"))
    assert len(fixtures) == 5, f"Expected 5 synthetic fixtures, found {len(fixtures)}"

    for f in fixtures:
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["fixture_type"] == "synthetic test fixture"
        assert "city" in data
        assert "lat" in data and "lon" in data
        assert len(data["places"]) >= 2
        for p_dict in data["places"]:
            p = Place.model_validate(p_dict)
            assert p.provenance.is_live is False
            assert p.provenance.is_estimate is True
