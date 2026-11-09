from datetime import date

import pytest

from app.etl import openstat, registry
from app.services import attribution


# --- PXWeb parsing (trap #1: csv, not json-stat2) ---------------------------

SAMPLE_CSV = (
    b'"Geolocation","Commodity","2024","2025"\n'
    b'"BENGUET","Cabbage","41.25","38.10"\n'
    b'"BENGUET","Carrot","35.00",".."\n'
)


def test_parse_csv_strips_quotes_and_bom():
    header, rows = openstat.parse_csv(b"\xef\xbb\xbf" + SAMPLE_CSV)
    assert header == ["Geolocation", "Commodity", "2024", "2025"]
    assert len(rows) == 2


def test_to_long_melts_period_columns():
    header, rows = openstat.parse_csv(SAMPLE_CSV)
    long = openstat.to_long(header, rows, n_key_columns=2)
    assert len(long) == 4
    assert long[0] == {
        "Geolocation": "BENGUET", "Commodity": "Cabbage",
        "period": "2024", "value": "41.25",
    }


def test_published_non_numeric_values_are_preserved_not_coerced():
    header, rows = openstat.parse_csv(SAMPLE_CSV)
    long = openstat.to_long(header, rows, n_key_columns=2)
    suppressed = [r for r in long if r["Commodity"] == "Carrot" and r["period"] == "2025"]
    assert suppressed[0]["value"] == ".."  # cleaning layer decides, not the parser


def test_empty_response_is_an_error():
    with pytest.raises(openstat.OpenStatError):
        openstat.parse_csv(b"")


# --- trap #2: resolve codes by label, every table ---------------------------

META = {
    "title": "Farmgate prices of leafy vegetables",
    "variables": [
        {
            "code": "Commodity",
            "values": ["0", "1", "2"],
            "valueTexts": ["Cabbage", "Carrot", "Potato"],
        }
    ],
}

OTHER_TABLE_META = {
    "title": "Volume of production",
    "variables": [
        {
            "code": "Commodity",
            # Same labels, DIFFERENT code indices. This is the trap.
            "values": ["7", "3", "9"],
            "valueTexts": ["Cabbage", "Carrot", "Potato"],
        }
    ],
}


def test_labels_resolve_to_this_tables_codes():
    assert openstat.resolve_codes_by_label(META, "Commodity", ["Cabbage", "Potato"]) == ["0", "2"]


def test_same_label_resolves_differently_in_a_different_table():
    a = openstat.resolve_codes_by_label(META, "Commodity", ["Carrot"])
    b = openstat.resolve_codes_by_label(OTHER_TABLE_META, "Commodity", ["Carrot"])
    assert a == ["1"] and b == ["3"]
    assert a != b, "codes must never be reused across tables"


def test_label_matching_is_case_and_space_insensitive():
    assert openstat.resolve_codes_by_label(META, "Commodity", ["  cabbage "]) == ["0"]


def test_unknown_label_fails_loudly_with_alternatives():
    with pytest.raises(openstat.VariableNotFound) as err:
        openstat.resolve_codes_by_label(META, "Commodity", ["Broccolli"])
    assert "Available" in str(err.value)


def test_query_body_requests_csv():
    body = openstat.build_query({"Commodity": ["0"]})
    assert body["response"]["format"] == "csv"


# --- series register --------------------------------------------------------

def test_series_id_is_deterministic_and_includes_grade():
    a = registry.SeriesKey("Cabbage", "farmgate_price", "1411", "monthly", "PHP/kg")
    b = registry.SeriesKey("cabbage", "farmgate_price", "1411", "monthly", "PHP/kg")
    assert a.series_id == b.series_id
    graded = registry.SeriesKey("Cabbage", "farmgate_price", "1411", "monthly", "PHP/kg", "Class A")
    assert graded.series_id != a.series_id


def test_invalid_variable_or_frequency_is_refused():
    with pytest.raises(ValueError):
        registry.SeriesKey("Cabbage", "yield", "1411", "monthly", "t/ha")
    with pytest.raises(ValueError):
        registry.SeriesKey("Cabbage", "production", "1411", "fortnightly", "t")


def test_freeze_hash_ignores_order_but_detects_shape_change():
    p = [date(2020, 1, 1), date(2020, 2, 1), date(2020, 3, 1)]
    assert registry.freeze_hash(p) == registry.freeze_hash(list(reversed(p)))
    assert registry.freeze_hash(p) != registry.freeze_hash(p + [date(2020, 4, 1)])


def test_verify_freeze_detects_a_changed_panel():
    p = [date(2020, 1, 1), date(2020, 2, 1)]
    h = registry.freeze_hash(p)
    assert registry.verify_freeze(h, p)
    assert not registry.verify_freeze(h, p + [date(2020, 3, 1)])


def test_empty_series_cannot_be_frozen():
    with pytest.raises(ValueError):
        registry.freeze_hash([])


def test_minimum_training_lengths_match_the_proposal():
    assert registry.min_observations("monthly") == 60
    assert registry.min_observations("quarterly") == 20
    assert registry.min_observations("annual") == 10


# --- CC BY compliance -------------------------------------------------------

def test_attribution_requires_a_statement_of_changes():
    with pytest.raises(ValueError):
        attribution.render("0032M4AFN06", "Farmgate prices", "2026-11-05", "   ")


def test_attribution_names_psa_the_table_and_the_licence():
    a = attribution.render(
        "0032M4AFN06", "Farmgate prices", "2026-11-05", attribution.STANDARD_MODIFICATIONS
    )
    assert "Philippine Statistics Authority" in a.text
    assert "0032M4AFN06" in a.text
    assert a.licence == "CC BY 4.0"
    assert "does not endorse" in a.text
