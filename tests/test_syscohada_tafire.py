# Copyright (c) 2026, Sitiame Capital
# License: MIT

"""Unit tests for TAFIRE, Tableau 1 and Tableau 2 — no database, no bench.
All frappe calls are monkeypatched via conftest.py.
"""

import datetime
import types

import pytest

from sitiame_core.syscohada_statements import (
    ACTIF_LINES,
    _assign_amort_code,
    _assign_immo_code,
    _bfe,
    _mv_credit,
    _mv_debit,
    _tresorerie_nette,
    compute_tableau1,
    compute_tableau2,
    compute_tafire,
    get_period_movements,
)


# ─── helpers shared across tests ─────────────────────────────────────────────

def _make_statements(
    td=0, ub=0, vb=0, wa=0, wb=0, rj=0, ua=0, va=0, rf=0,
    ba=0, bb=0, bc=0, ea=0, eb=0, ec_p=0, ed=0, ee=0,
    ca_a=0, cb_a=0, cc=0, fa_p=0, fb_p=0, fc_p=0,
    xz=0,
):
    """Build a minimal compute_statements()-like dict."""
    actif_net = {
        "AA": 0, "AB": 0, "AC": 0, "AD": 0, "AE": 0,
        "AF": 0, "AG": 0, "AH": 0, "AZ": 0,
        "BA": ba, "BB": bb, "BC": bc, "BZ": ba + bb + bc,
        "CA": ca_a, "CB": cb_a, "CC": cc, "CZ": ca_a + cb_a + cc,
        "DA": 0, "TA_ACTIF": 0,
    }
    passif = {
        "CA": 0, "CB": 0, "CC": 0, "CD": 0, "CE": 0, "CF": 0,
        "CG": xz, "CH": 0, "CI": 0, "CZ": 0,
        "DA": 0, "DB": 0, "DC": 0, "DZ": 0,
        "EA": ea, "EB": eb, "EC": ec_p, "ED": ed, "EE": ee,
        "EZ": ea + eb + ec_p + ed + ee,
        "FA": fa_p, "FB": fb_p, "FC": fc_p,
        "FZ": fa_p + fb_p + fc_p,
        "GA": 0, "TP_PASSIF": 0,
    }
    resultat = {
        "RA": 0, "RB": 0, "RC": 0, "RE": 0, "RF": rf, "RG": 0,
        "RH": 0, "RI": 0, "RJ": rj,
        "SA": 0, "SB": 0, "SC": 0, "SD": 0, "SE": 0,
        "SF": 0, "SG": 0, "SH": 0, "SI": 0, "SJ": 0, "SK": 0,
        "UA": ua, "UB": ub, "VA": va, "VB": vb,
        "WA": wa, "WB": wb,
        "TA": 0, "TB": 0, "TC": 0,
        "TD": td,  # EBE
        "TE": 0, "UC": 0, "UD": 0, "VC": 0,
        "XZ": xz,
    }
    return {
        "actif": {k: {"brut": 0.0, "amort": 0.0} for k in actif_net},
        "actif_net": actif_net,
        "passif": passif,
        "resultat": resultat,
        "unclassified": [],
        "unnumbered": [],
        "total_actif": 0,
        "total_passif": 0,
    }


# ─── get_period_movements ────────────────────────────────────────────────────

def test_get_period_movements_returns_dict(monkeypatch):
    import frappe
    monkeypatch.setattr(
        frappe.db, "sql",
        lambda *a, **k: [
            types.SimpleNamespace(account_number="211000", debit=500_000, credit=0),
            types.SimpleNamespace(account_number="281000", debit=0, credit=100_000),
        ],
    )
    from sitiame_core.syscohada_statements import get_period_movements
    result = get_period_movements("PME SA", "2026-01-01", "2026-12-31")
    assert result["211000"]["debit"] == 500_000
    assert result["211000"]["credit"] == 0
    assert result["281000"]["credit"] == 100_000


def test_get_period_movements_ignores_empty_number(monkeypatch):
    import frappe
    monkeypatch.setattr(
        frappe.db, "sql",
        lambda *a, **k: [
            types.SimpleNamespace(account_number="", debit=10_000, credit=0),
            types.SimpleNamespace(account_number=None, debit=5_000, credit=0),
            types.SimpleNamespace(account_number="40100", debit=200_000, credit=0),
        ],
    )
    from sitiame_core.syscohada_statements import get_period_movements
    result = get_period_movements("PME SA", "2026-01-01", "2026-12-31")
    assert "" not in result
    assert None not in result
    assert "40100" in result


# ─── helper functions ────────────────────────────────────────────────────────

def test_mv_debit_sums_matching_prefixes():
    mv = {"211000": {"debit": 300_000, "credit": 0},
          "212000": {"debit": 100_000, "credit": 50_000},
          "401000": {"debit": 20_000, "credit": 0}}
    assert _mv_debit(mv, "21") == 400_000
    assert _mv_debit(mv, "40") == 20_000
    assert _mv_debit(mv, "99") == 0


def test_mv_credit_sums_matching_prefixes():
    mv = {"281000": {"debit": 0, "credit": 120_000},
          "282000": {"debit": 0, "credit": 80_000},
          "211000": {"debit": 500_000, "credit": 10_000}}
    assert _mv_credit(mv, "28") == 200_000
    assert _mv_credit(mv, "21") == 10_000


def test_bfe_positive_when_actif_exceeds_passif():
    an = {"BA": 500_000, "BB": 200_000, "BC": 50_000,
          "CA": 0, "CB": 0, "CC": 0}
    p = {"EA": 100_000, "EB": 50_000, "EC": 30_000, "ED": 0, "EE": 0,
         "FA": 0, "FB": 0, "FC": 0}
    assert _bfe(an, p) == 570_000


def test_tresorerie_nette():
    an = {"CA": 50_000, "CB": 100_000, "CC": 800_000}
    p = {"FA": 200_000, "FB": 0, "FC": 0}
    assert _tresorerie_nette(an, p) == 750_000


# ─── assign codes ─────────────────────────────────────────────────────────────

def test_assign_immo_code_corporate():
    assert _assign_immo_code("23100") == "AD"   # Bâtiments
    assert _assign_immo_code("24000") == "AE"   # Matériel (24 générique)
    assert _assign_immo_code("24510") == "AF"   # Matériel transport (245 > 24)
    assert _assign_immo_code("21300") == "AB"   # Immo incorporelles


def test_assign_immo_code_financial():
    assert _assign_immo_code("26100") == "AG"
    assert _assign_immo_code("27500") == "AG"


def test_assign_immo_code_unrelated_returns_none():
    assert _assign_immo_code("40100") is None
    assert _assign_immo_code("70100") is None


def test_assign_amort_code_maps_correctly():
    assert _assign_amort_code("281000") == "AB"   # immo incorp amort
    assert _assign_amort_code("283000") == "AD"   # bâtiments amort
    assert _assign_amort_code("2845") == "AF"     # transport amort


def test_assign_amort_code_unrelated_returns_none():
    assert _assign_amort_code("40100") is None
    assert _assign_amort_code("21100") is None   # brut, not amort


# ─── compute_tafire ──────────────────────────────────────────────────────────

def _patch_tafire(monkeypatch, stmts_n, stmts_n1, mv=None):
    """Patch compute_statements and get_period_movements for TAFIRE tests."""
    import sitiame_core.syscohada_statements as mod
    call_count = [0]

    def fake_compute_statements(company, from_date, to_date):
        call_count[0] += 1
        # First call = N, second call = N-1
        return stmts_n if call_count[0] == 1 else stmts_n1

    monkeypatch.setattr(mod, "compute_statements", fake_compute_statements)
    monkeypatch.setattr(mod, "get_period_movements", lambda *a, **k: mv or {})


def test_cafg_basic(monkeypatch):
    sn = _make_statements(td=2_000_000, ub=300_000, vb=0, wa=100_000, wb=150_000,
                          rj=50_000, ua=80_000, va=0)
    sn1 = _make_statements()
    _patch_tafire(monkeypatch, sn, sn1)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31")
    expected_cafg = 2_000_000 - (300_000 + 0 + 100_000 + 150_000) + (50_000 + 80_000 + 0)
    assert result["cafg"] == pytest.approx(expected_cafg)


def test_af_deducts_dividendes(monkeypatch):
    sn = _make_statements(td=3_000_000)
    sn1 = _make_statements()
    _patch_tafire(monkeypatch, sn, sn1)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31", dividendes=500_000)
    assert result["af"] == pytest.approx(3_000_000 - 500_000)
    assert result["warning_dividendes"] is False


def test_warning_dividendes_when_zero(monkeypatch):
    sn = _make_statements(td=1_000_000)
    sn1 = _make_statements()
    _patch_tafire(monkeypatch, sn, sn1)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31")
    assert result["warning_dividendes"] is True


def test_variation_bfe(monkeypatch):
    # N: stocks 500k, créances 200k, dettes 300k  → BFE = 400k
    sn = _make_statements(ba=500_000, bb=200_000, bc=0, ea=300_000)
    # N-1: stocks 300k, créances 100k, dettes 200k → BFE = 200k
    sn1 = _make_statements(ba=300_000, bb=100_000, bc=0, ea=200_000)
    _patch_tafire(monkeypatch, sn, sn1)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31")
    # variation_stocks = 200k, variation_creances = 100k, variation_dettes = 100k
    # xc = 200k + 100k - 100k = 200k
    assert result["xc"] == pytest.approx(200_000)


def test_ete_formula(monkeypatch):
    sn = _make_statements(td=1_000_000, rf=50_000,
                          ba=500_000, bb=0, bc=0, ea=200_000)
    sn1 = _make_statements(ba=400_000, bb=0, bc=0, ea=200_000)
    _patch_tafire(monkeypatch, sn, sn1)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31")
    # xc = 100_000 (stocks augment de 100k, dettes inchangées)
    # xd = 1_000_000 - 100_000 - 50_000 = 850_000
    assert result["xd"] == pytest.approx(850_000)


def test_tresorerie_variation(monkeypatch):
    # N: CA=100k CC=900k FA_passif=200k → tréso nette = 800k
    sn = _make_statements(ca_a=100_000, cc=700_000, fa_p=0)
    # N-1: CC=500k → tréso nette = 500k
    sn1 = _make_statements(cc=500_000)
    _patch_tafire(monkeypatch, sn, sn1)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31")
    assert result["fu"] == pytest.approx(800_000)
    assert result["fv"] == pytest.approx(500_000)
    assert result["fw"] == pytest.approx(300_000)


def test_tafire_rows_have_required_keys(monkeypatch):
    sn = _make_statements()
    sn1 = _make_statements()
    _patch_tafire(monkeypatch, sn, sn1)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31")
    required = {"ref", "libelle", "emplois", "ressources", "bold", "indent", "section"}
    for row in result["rows"]:
        assert required <= row.keys(), f"Clés manquantes dans {row}"


def test_tafire_investissements_from_movements(monkeypatch):
    mv = {"211000": {"debit": 1_200_000, "credit": 0}}   # acquisition immo incorp
    sn = _make_statements()
    sn1 = _make_statements()
    _patch_tafire(monkeypatch, sn, sn1, mv=mv)

    result = compute_tafire("PME SA", "2026-01-01", "2026-12-31")
    # FB emplois = 1_200_000 − 0
    fb_row = next(r for r in result["rows"] if r["ref"] == "FB")
    assert fb_row["emplois"] == pytest.approx(1_200_000)
    assert fb_row["ressources"] == pytest.approx(0)


# ─── compute_tableau1 ────────────────────────────────────────────────────────

def _patch_tableau(monkeypatch, cumul, mv):
    import sitiame_core.syscohada_statements as mod

    def fake_get_account_balances(company, to_date, from_date=None):
        return cumul, []

    monkeypatch.setattr(mod, "get_account_balances", fake_get_account_balances)
    monkeypatch.setattr(mod, "get_period_movements", lambda *a, **k: mv)


def test_tableau1_cloture_equals_ouverture_plus_acquisitions_minus_cessions(monkeypatch):
    cumul = {"211000": 500_000}   # immo incorp opening
    mv = {"211000": {"debit": 200_000, "credit": 50_000}}  # acquis - cessions
    _patch_tableau(monkeypatch, cumul, mv)

    rows = compute_tableau1("PME SA", "2026-01-01", "2026-12-31")
    ab_row = next(r for r in rows if r["ref"] == "AB")
    assert ab_row["ouverture"] == pytest.approx(500_000)
    assert ab_row["acquisitions"] == pytest.approx(200_000)
    assert ab_row["cessions"] == pytest.approx(50_000)
    assert ab_row["cloture"] == pytest.approx(650_000)


def test_tableau1_total_row_sums_all_categories(monkeypatch):
    cumul = {"211000": 300_000, "231000": 700_000}
    mv = {}
    _patch_tableau(monkeypatch, cumul, mv)

    rows = compute_tableau1("PME SA", "2026-01-01", "2026-12-31")
    total_row = rows[-1]
    assert total_row["ref"] == "AZ"
    assert total_row["ouverture"] == pytest.approx(1_000_000)
    assert total_row["cloture"] == pytest.approx(1_000_000)


def test_tableau1_245_goes_to_af_not_ae(monkeypatch):
    """Matériel de transport (245x) doit aller sur AF, pas AE."""
    cumul = {"24500": 400_000, "24000": 100_000}
    mv = {}
    _patch_tableau(monkeypatch, cumul, mv)

    rows = compute_tableau1("PME SA", "2026-01-01", "2026-12-31")
    ae_row = next(r for r in rows if r["ref"] == "AE")
    af_row = next(r for r in rows if r["ref"] == "AF")
    assert ae_row["ouverture"] == pytest.approx(100_000)
    assert af_row["ouverture"] == pytest.approx(400_000)


def test_tableau1_rows_have_required_keys(monkeypatch):
    _patch_tableau(monkeypatch, {}, {})
    rows = compute_tableau1("PME SA", "2026-01-01", "2026-12-31")
    required = {"ref", "libelle", "bold", "indent", "ouverture",
                "acquisitions", "cessions", "cloture"}
    for row in rows:
        assert required <= row.keys(), f"Clés manquantes : {row}"


# ─── compute_tableau2 ────────────────────────────────────────────────────────

def test_tableau2_cumul_cloture_formula(monkeypatch):
    # 281000: cumul opening = 300_000 crédit → balance = -300_000
    cumul = {"281000": -300_000}
    mv = {"281000": {"debit": 0, "credit": 120_000}}   # nouvelles dotations
    _patch_tableau(monkeypatch, cumul, mv)

    rows = compute_tableau2("PME SA", "2026-01-01", "2026-12-31")
    ab_row = next(r for r in rows if r["ref"] == "AB")
    assert ab_row["cumul_ouverture"] == pytest.approx(300_000)
    assert ab_row["dotations"] == pytest.approx(120_000)
    assert ab_row["sorties"] == pytest.approx(0)
    assert ab_row["cumul_cloture"] == pytest.approx(420_000)


def test_tableau2_sorties_on_asset_disposal(monkeypatch):
    cumul = {"283000": -500_000}   # bâtiments amort
    mv = {"283000": {"debit": 200_000, "credit": 50_000}}   # extourne + dotation
    _patch_tableau(monkeypatch, cumul, mv)

    rows = compute_tableau2("PME SA", "2026-01-01", "2026-12-31")
    ad_row = next(r for r in rows if r["ref"] == "AD")
    assert ad_row["sorties"] == pytest.approx(200_000)
    assert ad_row["dotations"] == pytest.approx(50_000)
    assert ad_row["cumul_cloture"] == pytest.approx(500_000 + 50_000 - 200_000)


def test_tableau2_total_row_is_last(monkeypatch):
    _patch_tableau(monkeypatch, {}, {})
    rows = compute_tableau2("PME SA", "2026-01-01", "2026-12-31")
    assert rows[-1]["ref"] == "AZ"
    assert rows[-1]["bold"] == 1


def test_tableau2_rows_have_required_keys(monkeypatch):
    _patch_tableau(monkeypatch, {}, {})
    rows = compute_tableau2("PME SA", "2026-01-01", "2026-12-31")
    required = {"ref", "libelle", "bold", "indent",
                "cumul_ouverture", "dotations", "sorties", "cumul_cloture"}
    for row in rows:
        assert required <= row.keys(), f"Clés manquantes : {row}"
