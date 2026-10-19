# -*- coding: utf-8 -*-
"""Tests de la méthode Cristofori_Mucchi (pytest) :  python -m pytest tests"""

import math
import os
import sys

import numpy as np
import pytest

DOSSIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DOSSIER)

import calculs  # noqa: E402
import config  # noqa: E402
import data_io  # noqa: E402
import methode  # noqa: E402


def test_independance_modules():
    """Aucun module n'est importé depuis un autre dossier que le programme."""
    for nom in ("calculs", "config", "data_io", "methode",
                "selection_capteurs"):
        fichier = os.path.abspath(sys.modules[nom].__file__) \
            if nom in sys.modules else DOSSIER
        assert os.path.dirname(fichier) == DOSSIER


def test_lv_lvib_lvib_global_et_delta():
    niveaux = [[60.0, 50.0], [60.0, 56.0]]   # 2 capteurs, 2 bandes
    combis = np.array([[0, 1]])
    lv = calculs.niveaux_combinaisons(niveaux, combis)
    attendu_b2 = 10 * math.log10((10 ** 5.0 + 10 ** 5.6) / 2)
    assert lv[0, 0] == pytest.approx(60.0)
    assert lv[0, 1] == pytest.approx(attendu_b2)
    terme = 10 * math.log10(config.S / config.S0) + 10 * math.log10(
        config.ZC / config.ZC0)
    lvib_j = calculs.niveaux_vibratoires(lv)
    assert lvib_j[0, 0] == pytest.approx(60.0 + terme)
    lvib = calculs.niveau_global(lvib_j)
    assert lvib[0] == pytest.approx(10 * math.log10(
        10 ** ((60.0 + terme) / 10) + 10 ** ((attendu_b2 + terme) / 10)))
    ev = calculs.evaluer_excitation(niveaux, combis, np.array([55.0, 50.0]),
                                    62.0)
    assert ev["delta"][0] == pytest.approx(abs(lvib[0] - 62.0))


def test_indice_similarite():
    lac = np.array([50.0, 40.0])
    lvib = np.array([[48.0, 44.0]])
    attendu = (math.sqrt(2 * 50) + math.sqrt(4 * 40)) / 90.0
    assert calculs.indice_similarite(lac, lvib)[0] == pytest.approx(attendu)
    with pytest.raises(calculs.ErreurCalcul):
        calculs.indice_similarite(np.array([-1.0, 40.0]), lvib)


def test_facteur_rayonnement():
    sigma = calculs.facteur_rayonnement(np.array([60.0]), np.array([[57.0]]))
    assert sigma[0, 0] == pytest.approx(10 ** 0.3)


def test_incertitude_lac_et_rayonnement():
    runs = [[50.0], [52.0], [51.0]]
    moy = 10 * math.log10(np.mean([10 ** 5.0, 10 ** 5.2, 10 ** 5.1]))
    s = math.sqrt(sum((x - moy) ** 2 for x in (50.0, 52.0, 51.0)) / 2)
    u = calculs.incertitude_lac(runs, [500.0])
    assert u[0] == pytest.approx(2.0 * math.sqrt(s ** 2 + 1.5 ** 2))
    assert calculs.incertitude_facteur_rayonnement(
        np.array([2.0]), np.array([3.0]))[0] == pytest.approx(
        math.log(10) / 10 * 2.0 * 3.0)


def test_bande_hors_plage_et_un_seul_run():
    with pytest.raises(calculs.ErreurCalcul):
        calculs.terme_s_r0(180.0)          # entre 160 et 200 Hz
    with pytest.raises(calculs.ErreurCalcul):
        calculs.incertitude_lac([[50.0]], [500.0])


def test_moyenne_gum():
    moy, u = calculs.moyenne_facteurs_excitations(
        [[1.0], [3.0]], [[0.3], [0.4]])
    assert moy[0] == pytest.approx(2.0)
    assert u[0] == pytest.approx(math.sqrt(0.3 ** 2 + 0.4 ** 2) / 2)


def test_combinaisons_binome():
    assert len(calculs.generer_combinaisons(6, 3)) == math.comb(6, 3)


def _configurer(monkeypatch, tmp_path, **valeurs):
    monkeypatch.setattr(config, "FICHIER_SORTIE", str(tmp_path / "out.json"))
    monkeypatch.setattr(config, "DOSSIER_FIGURES", str(tmp_path / "fig"))
    monkeypatch.setattr(config, "RANDOM_SEED", 12345)
    for cle, valeur in valeurs.items():
        monkeypatch.setattr(config, cle, valeur)


def test_plusieurs_excitations_plusieurs_n_et_tests(monkeypatch, tmp_path):
    _configurer(monkeypatch, tmp_path, N_CAPTEUR_COMBINAISON=[3, 2], Nb_Test=2,
                TARGET_VALUE=3)
    res = methode.executer(journal=lambda *_: None)
    racine = res["DataCristofori"]
    assert list(racine) == ["n_equal_2", "n_equal_3"]
    for bloc_n in racine.values():
        assert list(bloc_n) == ["TEST1", "TEST2"]
        for test in bloc_n.values():
            assert {"Data_k", "Data_k_prime_m", "Data_k_prime",
                    "Data_k_2prime", "Data_Accel", "Data_Acou"} <= set(test)
            exc = test["Data_k_2prime"]["EXCITATION1"]
            assert exc["Data_Delta_mk"] < 3
    assert "Metadata" in res


def test_une_excitation_et_exclusions(monkeypatch, tmp_path):
    _configurer(monkeypatch, tmp_path, EXCITATIONS_A_EXCLURE=[1, 2],
                TARGET_VALUE=3)
    res = methode.executer(journal=lambda *_: None)
    assert list(res)[0] == "DataCristofori_EXC3"
    test = res["DataCristofori_EXC3"]["n_equal_2"]["TEST1"]
    assert "Data_k_prime" not in test
    assert test["Data_k_2prime"]["EXCITATION3"]["Spectral_Similarity_m"] >= 0
    import figures
    n = figures.tracer(res, journal=lambda *_: None)
    assert n == 6
    assert os.path.isdir(tmp_path / "fig" / "n_equal_2" / "TEST1")


def test_k_prime_vide_limite_relances(monkeypatch, tmp_path):
    import selection_capteurs as sel
    _configurer(monkeypatch, tmp_path, TARGET_VALUE=1e-9, MAX_RELANCES_K_PRIME=2)
    with pytest.raises(sel.SelectionImpossible, match="MAX_RELANCES_K_PRIME"):
        methode.executer(journal=lambda *_: None)


def test_exclusion_inconnue(monkeypatch, tmp_path):
    _configurer(monkeypatch, tmp_path, EXCITATIONS_A_EXCLURE=[9])
    with pytest.raises(data_io.ErreurDonnees):
        methode.executer(journal=lambda *_: None)


def test_n_invalide(monkeypatch, tmp_path):
    _configurer(monkeypatch, tmp_path, N_CAPTEUR_COMBINAISON=[])
    with pytest.raises(methode.ErreurConfiguration):
        methode.executer(journal=lambda *_: None)
