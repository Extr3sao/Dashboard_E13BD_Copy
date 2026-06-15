from src.api.post_crq_audit import _build_annex_entries_v2
from src.core.check_explanation_catalog import load_check_explanation_catalog


def test_annex_entries_v2_do_not_merge_sections_into_each_other():
    report = {
        "executed_checks": [
            {
                "check_id": "CHECK_06",
                "title": "ÍNDEXS DUPLICATS RECENTS (MATEIXA COLUMNA LÍDER)",
                "severitat": "Mitjà",
            }
        ]
    }

    entry = _build_annex_entries_v2(report)[0]

    assert "Columnes recomanades per interpretar el resultat:" not in entry["com_revisar"]
    assert "Limitacions i matisos del control:" not in entry["validacio_posterior"]


def test_refined_catalog_entries_keep_requested_guardrails():
    catalog = load_check_explanation_catalog()

    check_02 = catalog["CHECK_02"]
    assert "volum" in check_02["impacte_sobre_lot"].casefold()
    assert "ús" in check_02["limitacions"].casefold()

    check_06 = catalog["CHECK_06"]
    assert "No s'ha d'eliminar directament" in check_06["com_corregir"]
    assert "plans d'execució" in check_06["validacio_posterior"]

    check_11 = catalog["CHECK_11"]
    merged_11 = " ".join(
        [
            check_11["que_detecta"],
            check_11["com_revisar"],
            check_11["validacio_posterior"],
        ]
    )
    assert "requereix validació manual" in merged_11

    check_12 = catalog["CHECK_12"]
    merged_12 = " ".join(
        [
            check_12["que_detecta"],
            check_12["com_revisar"],
            check_12["com_corregir"],
            check_12["validacio_posterior"],
        ]
    )
    assert "freqüència" in merged_12
    assert "cost de refactorització" in merged_12
