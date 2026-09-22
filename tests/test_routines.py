# -*- coding: utf-8 -*-
"""Tests des routines ISO 7849-1 et ISO 7849-2 sur signaux artificiels.

Les jeux de données utilisés ici sont fabriqués de toutes pièces, avec des
niveaux dont le résultat attendu est connu analytiquement : c'est ce qui permet
de vérifier les formules (moyenne énergétique, niveau global, facteur de
rayonnement) au lieu de se contenter de comparer le programme à lui-même.

Lancement :
    python -m pytest -v            (depuis le dossier CALCULDATA)
"""

from __future__ import annotations

import json
import math
import os
import random

import pytest

import calculs
import config
import data_io
import pipeline
import selection_capteurs as selection


# ---------------------------------------------------------------------------
# Générateur de jeux de mesures artificiels
# ---------------------------------------------------------------------------

def jeu_artificiel(n_capteurs=30, n_bandes=5, n_excitations=3,
                   niveau_base=70.0, dispersion_db=2.0, graine=12345,
                   sigma_cible=None, avec_champ_parasite=True):
    """Construit un dictionnaire de mesures au format DataMesure2_v01.

    * les capteurs sont répartis sur une grille régulière (coordonnées XYZ) ;
    * les niveaux vibratoires oscillent dans une plage de `dispersion_db`
      autour de `niveau_base`, ce qui garantit que le critère max/min est
      satisfiable (écart < 5 capteurs) ;
    * si `sigma_cible` est fourni, le spectre acoustique est construit pour que
      le facteur de rayonnement calculé vaille exactement cette valeur, bande
      par bande, lorsque TOUS les capteurs sont pris en compte ;
    * `avec_champ_parasite` ajoute un champ Data_3rdOctaveMean_Vel volontairement
      faux dans le fichier source : le programme ne doit jamais l'utiliser.
    """
    generateur = random.Random(graine)
    frequences = [100.0 * (2.0 ** (indice / 3.0)) for indice in range(n_bandes)]
    frequences = [round(frequence, 1) for frequence in frequences]
    noms = ["Accel%02d" % (indice + 1) for indice in range(n_capteurs)]

    cote = int(math.ceil(math.sqrt(n_capteurs)))
    coordonnees = []
    for indice in range(n_capteurs):
        coordonnees.append([
            float((indice % cote) * 100),
            float((indice // cote) * 100),
            float(50 * (indice % 3)),
        ])

    donnees = {"BDF": {"Accel": {"frq_3rdOctave": list(frequences)},
                       "Micro": {"frq_3rdOctave": list(frequences)}}}

    for numero in range(1, n_excitations + 1):
        niveaux = []
        for _ in range(n_capteurs):
            niveaux.append([
                niveau_base + numero
                + generateur.uniform(-dispersion_db / 2.0, dispersion_db / 2.0)
                for _ in range(n_bandes)
            ])

        moyennes = [
            calculs.moyenne_energetique([ligne[bande] for ligne in niveaux])
            for bande in range(n_bandes)
        ]
        vib = calculs.spectre_vib_iso1(moyennes)
        if sigma_cible is None:
            spectre_acou = [valeur - 10.0 for valeur in vib]
        else:
            spectre_acou = [
                valeur + 10.0 * math.log10(sigma_cible[bande])
                for bande, valeur in enumerate(vib)
            ]

        accel = {
            "frq_3rdOctave": list(frequences),
            "sensor_name": list(noms),
            "sensor_coordinates": [list(point) for point in coordonnees],
            "Data_3rdOctave_Vel": niveaux,
        }
        if avec_champ_parasite:
            # Valeur absurde : si elle apparaît dans les résultats, le
            # programme a utilisé le champ du fichier au lieu de recalculer.
            accel["Data_3rdOctaveMean_Vel"] = [-999.0] * n_bandes
        donnees["EXCITATION%d" % numero] = {
            "Accel": accel,
            "Micro": {
                "frq_3rdOctave": list(frequences),
                "Data_3rdOctave_Lw": spectre_acou,
                "Data_GlobalLevel_Lw": calculs.niveau_global(spectre_acou),
            },
        }
    return donnees


def ecrire_jeu(dossier, donnees, nom="mesures_artificielles.json"):
    chemin = os.path.join(str(dossier), nom)
    with open(chemin, "w", encoding="utf-8") as flux:
        json.dump(donnees, flux)
    return chemin


@pytest.fixture
def config_par_defaut(monkeypatch):
    """Rétablit une configuration connue pour chaque test."""
    monkeypatch.setattr(config, "S", 0.369286)
    monkeypatch.setattr(config, "S0", 1.0)
    monkeypatch.setattr(config, "ZC", 411.0)
    monkeypatch.setattr(config, "ZC0", 400.0)
    monkeypatch.setattr(config, "W0", 1e-12)
    monkeypatch.setattr(config, "Sigma_Ref", 1.0)
    monkeypatch.setattr(config, "CapteursCommuns", 0.5)
    monkeypatch.setattr(config, "CAPTEURS_EXCLUS", [])
    monkeypatch.setattr(config, "SEUIL_ECART_DB", None)
    monkeypatch.setattr(config, "MAX_TENTATIVES_PAR_TEST", 50)
    monkeypatch.setattr(config, "Excitations_RF", [1])
    monkeypatch.setattr(config, "RANDOM_SEED", 2024)
    monkeypatch.setattr(config, "Nb_Test", 3)
    return config


# ---------------------------------------------------------------------------
# 1. Lecture et validation
# ---------------------------------------------------------------------------

def test_excitations_triees_numeriquement():
    donnees = {"EXCITATION10": {}, "EXCITATION2": {}, "EXCITATION1": {},
               "BDF": {}, "EXCITATION11": {}}
    assert data_io.lister_excitations(donnees) == [
        "EXCITATION1", "EXCITATION2", "EXCITATION10", "EXCITATION11"
    ]


def test_validation_jeu_correct(config_par_defaut):
    resume = data_io.valider_mesures(jeu_artificiel(), n_capteurs_min=10)
    assert len(resume["excitations"]) == 3
    assert len(resume["capteurs"]) == 30
    assert len(resume["frequences"]) == 5


def test_validation_signale_champ_absent(config_par_defaut):
    donnees = jeu_artificiel()
    del donnees["EXCITATION2"]["Accel"]["sensor_coordinates"]
    with pytest.raises(data_io.ErreurDonnees) as erreur:
        data_io.valider_mesures(donnees)
    assert "sensor_coordinates" in str(erreur.value)
    assert "EXCITATION2" in str(erreur.value)


def test_validation_signale_valeur_non_finie(config_par_defaut):
    donnees = jeu_artificiel()
    donnees["EXCITATION1"]["Accel"]["Data_3rdOctave_Vel"][3][2] = float("nan")
    with pytest.raises(data_io.ErreurDonnees) as erreur:
        data_io.valider_mesures(donnees)
    assert "nombre fini" in str(erreur.value)


def test_validation_signale_dimension_incoherente(config_par_defaut):
    donnees = jeu_artificiel()
    donnees["EXCITATION1"]["Accel"]["Data_3rdOctave_Vel"][0].append(60.0)
    with pytest.raises(data_io.ErreurDonnees):
        data_io.valider_mesures(donnees)


def test_validation_nombre_de_capteurs_insuffisant(config_par_defaut):
    donnees = jeu_artificiel(n_capteurs=4)
    with pytest.raises(data_io.ErreurDonnees) as erreur:
        data_io.valider_mesures(donnees, n_capteurs_min=5)
    assert "combinaison initiale" in str(erreur.value)


def test_capteurs_exclus_retires_et_controles(config_par_defaut, monkeypatch):
    noms = ["Accel01", "Accel02", "Accel03"]
    monkeypatch.setattr(config, "CAPTEURS_EXCLUS", ["Accel02"])
    assert data_io.indices_capteurs_disponibles(noms) == [0, 2]
    monkeypatch.setattr(config, "CAPTEURS_EXCLUS", ["Accel99"])
    with pytest.raises(data_io.ErreurDonnees) as erreur:
        data_io.indices_capteurs_disponibles(noms)
    assert "Accel99" in str(erreur.value)


# ---------------------------------------------------------------------------
# 2. Calculs sur signaux artificiels à résultat connu
# ---------------------------------------------------------------------------

def test_moyenne_energetique_de_niveaux_identiques():
    assert calculs.moyenne_energetique([80.0] * 7) == pytest.approx(80.0)


def test_moyenne_energetique_valeur_analytique():
    # 10*log10((10^8 + 10^9)/2) = 10*log10(5.5e8)
    attendu = 10.0 * math.log10((10.0 ** 8 + 10.0 ** 9) / 2.0)
    assert calculs.moyenne_energetique([80.0, 90.0]) == pytest.approx(attendu)


def test_somme_energetique_de_n_niveaux_identiques():
    # n niveaux identiques : L + 10*log10(n)
    assert calculs.somme_energetique([60.0] * 10) == pytest.approx(70.0)
    assert calculs.niveau_global([60.0] * 4) == pytest.approx(
        60.0 + 10.0 * math.log10(4)
    )


def test_moyenne_energetique_liste_vide():
    with pytest.raises(ValueError):
        calculs.moyenne_energetique([])


def test_terme_surface_impedance(config_par_defaut, monkeypatch):
    # ZC = ZC0 : le terme se réduit à 10*log10(S/S0)
    monkeypatch.setattr(config, "ZC0", 411.0)
    attendu = 10.0 * math.log10(0.369286)
    assert calculs.terme_surface_impedance() == pytest.approx(attendu)
    monkeypatch.setattr(config, "ZC", 822.0)
    assert calculs.terme_surface_impedance() == pytest.approx(
        attendu + 10.0 * math.log10(2.0)
    )
    monkeypatch.setattr(config, "S", -1.0)
    with pytest.raises(ValueError):
        calculs.terme_surface_impedance()


def test_spectre_moyen_ignore_les_capteurs_hors_combinaison(config_par_defaut):
    niveaux = [[80.0, 80.0], [80.0, 80.0], [200.0, 200.0]]
    moyenne = calculs.spectre_moyen_vel(niveaux, [0, 1])
    assert moyenne == pytest.approx([80.0, 80.0])


def test_spectre_vib_iso1_ajoute_le_terme_constant(config_par_defaut):
    terme = calculs.terme_surface_impedance()
    spectre = calculs.spectre_vib_iso1([70.0, 75.0, 80.0])
    assert spectre == pytest.approx([70.0 + terme, 75.0 + terme, 80.0 + terme])


def test_facteur_rayonnement_retrouve_la_valeur_imposee(config_par_defaut):
    # Signal artificiel : Acou = Vib + 10*log10(sigma) -> sigma retrouvé
    sigma = [0.25, 1.0, 4.0]
    moyennes = [70.0, 72.0, 74.0]
    vib = calculs.spectre_vib_iso1(moyennes)
    acou = [valeur + 10.0 * math.log10(sigma[bande])
            for bande, valeur in enumerate(vib)]
    assert calculs.facteur_rayonnement_excitation(moyennes, acou) == \
        pytest.approx(sigma)


def test_moyenne_arithmetique_des_facteurs():
    moyenne = calculs.moyenne_facteurs_rayonnement([[1.0, 2.0], [3.0, 6.0]])
    assert moyenne == pytest.approx([2.0, 4.0])
    with pytest.raises(ValueError):
        calculs.moyenne_facteurs_rayonnement([])


def test_spectre_vib_iso2_corrige_du_facteur(config_par_defaut):
    moyennes = [70.0, 70.0]
    sigma = [1.0, 10.0]
    iso1 = calculs.spectre_vib_iso1(moyennes)
    iso2 = calculs.spectre_vib_iso2(moyennes, sigma)
    assert iso2[0] == pytest.approx(iso1[0])           # sigma = 1 : pas d'effet
    assert iso2[1] == pytest.approx(iso1[1] + 10.0)    # sigma = 10 : +10 dB


def test_facteur_rayonnement_calcule_sur_tous_les_capteurs(config_par_defaut):
    sigma = [0.5, 1.5, 2.0, 0.8, 1.2]
    donnees = jeu_artificiel(n_capteurs=20, n_bandes=5, sigma_cible=sigma)
    tous = list(range(20))
    facteur, detail = calculs.calculer_facteur_rayonnement(
        donnees, data_io.lister_excitations(donnees), data_io.donnees_accel,
        data_io.donnees_micro, tous, excitations_rf=[1],
    )
    assert facteur == pytest.approx(sigma)
    assert list(detail) == ["EXCITATION1"]


def test_facteur_rayonnement_moyenne_plusieurs_excitations(config_par_defaut):
    sigma = [1.0, 2.0, 3.0, 4.0, 5.0]
    donnees = jeu_artificiel(n_capteurs=15, n_bandes=5, n_excitations=3,
                             sigma_cible=sigma)
    tous = list(range(15))
    facteur, detail = calculs.calculer_facteur_rayonnement(
        donnees, data_io.lister_excitations(donnees), data_io.donnees_accel,
        data_io.donnees_micro, tous, excitations_rf=[1, 3],
    )
    # Chaque excitation ayant le même sigma imposé, la moyenne vaut sigma.
    assert facteur == pytest.approx(sigma)
    assert len(detail) == 2


def test_facteur_rayonnement_excitation_absente(config_par_defaut):
    donnees = jeu_artificiel(n_excitations=2)
    with pytest.raises(ValueError) as erreur:
        calculs.calculer_facteur_rayonnement(
            donnees, data_io.lister_excitations(donnees),
            data_io.donnees_accel, data_io.donnees_micro, list(range(30)),
            excitations_rf=[7],
        )
    assert "absente" in str(erreur.value)


# ---------------------------------------------------------------------------
# 3. Critère max/min et sélection
# ---------------------------------------------------------------------------

def test_ecarts_par_bande():
    niveaux = [[70.0, 60.0], [75.0, 61.0], [72.0, 58.0]]
    ecarts, maxima, minima = selection.ecarts_par_bande(niveaux, [0, 1, 2])
    assert ecarts == pytest.approx([5.0, 3.0])
    assert maxima == pytest.approx([75.0, 61.0])
    assert minima == pytest.approx([70.0, 58.0])


def test_critere_compare_a_n(config_par_defaut):
    assert selection.critere_satisfait([4.9], 5) is True
    assert selection.critere_satisfait([5.0], 5) is False   # strictement <
    assert selection.critere_satisfait([4.0, 6.0], 5) is False


def test_critere_avec_facteur_de_la_norme(config_par_defaut):
    # ISO/TS 7849-1, 7.3 : le seuil vaut le DOUBLE du nombre de positions.
    assert selection.seuil_critere(5, facteur=2.0) == 10.0
    assert selection.critere_satisfait([9.5], 5, facteur=2.0) is True
    assert selection.critere_satisfait([9.5], 5, facteur=1.0) is False
    # ISO/TS 7849-2, 7.3 : le seuil vaut le nombre de positions.
    assert selection.seuil_critere(10, facteur=1.0) == 10.0


def test_table1_nombre_de_positions_initiales(config_par_defaut, monkeypatch):
    # Surface de l'étude : 0,369286 m2, donc S < 1 m2.
    assert calculs.positions_initiales_table1(1) == 5
    assert calculs.positions_initiales_table1(2) == 10
    # 1 <= S <= 10 m2
    assert calculs.positions_initiales_table1(1, S=4.0) == 10
    assert calculs.positions_initiales_table1(2, S=4.0) == 20
    # S > 10 m2 : S/S0 pour la partie 1, 2*S/S0 pour la partie 2
    assert calculs.positions_initiales_table1(1, S=12.5) == 13
    assert calculs.positions_initiales_table1(2, S=12.5) == 25
    with pytest.raises(ValueError):
        calculs.positions_initiales_table1(3)


def test_terme_impedance_de_la_norme(config_par_defaut, monkeypatch):
    # Equations (12) et (15) : 10*log10(411/Zc,0) avec Zc,0 = 400 N.s/m3.
    monkeypatch.setattr(config, "ZC0", 400.0)
    attendu = 10.0 * math.log10(config.S / config.S0) \
        + 10.0 * math.log10(411.0 / 400.0)
    assert calculs.terme_surface_impedance() == pytest.approx(attendu)
    # L'écart avec la valeur ZC0 = 411 du cahier des charges vaut 0,12 dB.
    monkeypatch.setattr(config, "ZC0", 411.0)
    assert attendu - calculs.terme_surface_impedance() == \
        pytest.approx(0.118, abs=0.005)


def test_seuil_derogatoire(config_par_defaut, monkeypatch):
    monkeypatch.setattr(config, "SEUIL_ECART_DB", 12.0)
    assert selection.seuil_critere(5) == 12.0
    assert selection.critere_satisfait([11.0], 5) is True


def test_seuil_fixe_abandonne_sans_ajouter(config_par_defaut, monkeypatch):
    # Avec un seuil fixe, ajouter un capteur ne peut qu'augmenter l'écart :
    # la combinaison est abandonnée immédiatement, sans ajout inutile.
    monkeypatch.setattr(config, "SEUIL_ECART_DB", 3.0)
    niveaux = [[70.0], [80.0], [71.0], [72.0]]
    coordonnees = [[float(i), 0.0, 0.0] for i in range(4)]
    combinaison = [0, 1]
    with pytest.raises(selection.CritereInatteignable) as erreur:
        selection.traiter_excitation(
            niveaux, coordonnees, [0, 1, 2, 3], combinaison, random.Random(0)
        )
    assert "seuil fixe" in str(erreur.value)
    assert combinaison == [0, 1]        # aucun capteur ajouté


def test_taux_acceptation_initiale(config_par_defaut, monkeypatch):
    monkeypatch.setattr(config, "SEUIL_ECART_DB", 3.0)
    coordonnees = [[float(i), 0.0, 0.0] for i in range(6)]
    # Écarts de 1 dB au plus : tous les tirages passent.
    faciles = {"EXCITATION1": [[70.0], [70.5], [71.0], [70.2], [70.8], [70.1]]}
    estimation = selection.taux_acceptation_initiale(
        faciles, coordonnees, list(range(6)), 3, random.Random(1), n_essais=40
    )
    assert estimation["taux"] == 1.0
    # Écarts de 30 dB : aucun tirage ne passe.
    durs = {"EXCITATION1": [[40.0], [70.0], [55.0], [41.0], [69.0], [56.0]]}
    estimation = selection.taux_acceptation_initiale(
        durs, coordonnees, list(range(6)), 3, random.Random(1), n_essais=40
    )
    assert estimation["taux"] == 0.0
    assert estimation["meilleur_ecart"] > 3.0


def test_diagnostic_ne_conclut_pas_en_seuil_fixe(config_par_defaut,
                                                 monkeypatch):
    monkeypatch.setattr(config, "SEUIL_ECART_DB", 10.0)
    impossible = {"EXCITATION1": [[30.0], [71.0], [72.0], [70.5]]}
    diagnostic = selection.diagnostic_faisabilite(impossible, [0, 1, 2, 3])
    assert diagnostic["mode"] == "seuil_fixe"
    assert diagnostic["faisable"] is True       # dépend du tirage, pas global


def test_ajout_un_capteur_a_la_fois_et_conservation(config_par_defaut):
    # Bande unique : les capteurs 0 et 1 sont écartés de 6 dB, donc le critère
    # n'est pas satisfait à n = 2 ; les capteurs suivants sont intermédiaires,
    # le seuil devient atteignable après quelques ajouts.
    niveaux = [[70.0], [76.0], [72.0], [73.0], [74.0], [75.0], [71.0]]
    coordonnees = [[float(indice), 0.0, 0.0] for indice in range(7)]
    generateur = random.Random(7)
    combinaison = [0, 1]
    resultat, ajouts = selection.traiter_excitation(
        niveaux, coordonnees, list(range(7)), combinaison, generateur
    )
    assert resultat is combinaison              # liste modifiée sur place
    assert combinaison[:2] == [0, 1]            # capteurs conservés
    assert len(set(combinaison)) == len(combinaison)   # aucun doublon
    assert len(ajouts) == len(combinaison) - 2
    ecarts, _, _ = selection.ecarts_par_bande(niveaux, combinaison)
    assert selection.critere_satisfait(ecarts, len(combinaison))


def test_critere_inatteignable_leve_une_exception(config_par_defaut):
    # Deux capteurs seulement, écart de 40 dB : aucune combinaison ne convient.
    niveaux = [[30.0], [70.0]]
    coordonnees = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    with pytest.raises(selection.CritereInatteignable):
        selection.traiter_excitation(
            niveaux, coordonnees, [0, 1], [0, 1], random.Random(1)
        )


def test_diagnostic_faisabilite(config_par_defaut):
    coordonnees = [[float(i), 0.0, 0.0] for i in range(4)]
    del coordonnees
    possible = {"EXCITATION1": [[70.0], [71.0], [72.0], [70.5]]}
    impossible = {"EXCITATION1": [[30.0], [71.0], [72.0], [70.5]]}
    assert selection.diagnostic_faisabilite(possible, [0, 1, 2, 3])["faisable"]
    diagnostic = selection.diagnostic_faisabilite(impossible, [0, 1, 2, 3])
    assert diagnostic["faisable"] is False
    assert diagnostic["ecart_maximal"] == pytest.approx(42.0)
    assert diagnostic["bandes_bloquantes"][0][0] == "EXCITATION1"


def test_selection_initiale_respecte_les_exclusions(config_par_defaut):
    coordonnees = [[float(i), 0.0, 0.0] for i in range(10)]
    disponibles = [0, 1, 2, 5, 8, 9]
    for graine in range(20):
        selectionnes = selection.selection_initiale(
            coordonnees, disponibles, 4, random.Random(graine)
        )
        assert len(selectionnes) == 4
        assert len(set(selectionnes)) == 4
        assert set(selectionnes) <= set(disponibles)


def test_selection_initiale_favorise_la_dispersion(config_par_defaut):
    # Huit capteurs groupés à l'origine, deux capteurs éloignés : un tirage
    # dispersé retient les capteurs éloignés bien plus souvent qu'un tirage
    # uniforme (qui les prendrait dans 2 cas sur 10 en moyenne).
    coordonnees = [[float(indice) * 0.1, 0.0, 0.0] for indice in range(8)]
    coordonnees += [[500.0, 0.0, 0.0], [0.0, 500.0, 0.0]]
    disponibles = list(range(10))
    eloignes = 0
    for graine in range(200):
        selectionnes = selection.selection_initiale(
            coordonnees, disponibles, 3, random.Random(graine)
        )
        eloignes += len({8, 9} & set(selectionnes))
    # Tirage uniforme : environ 0.6 capteur éloigné par tirage de 3.
    assert eloignes / 200.0 > 1.2


def test_selection_reste_aleatoire(config_par_defaut):
    coordonnees = [[float(i), float(i % 3), 0.0] for i in range(20)]
    tirages = {
        tuple(sorted(selection.selection_initiale(
            coordonnees, list(range(20)), 5, random.Random(graine))))
        for graine in range(30)
    }
    assert len(tirages) > 5     # les tirages ne sont pas déterministes


def test_doublon_denominateur_plus_petite_combinaison(config_par_defaut):
    precedente = [1, 2, 3, 4, 5, 6, 7, 8]
    # Combinaison de 4 capteurs, 3 en commun : 3 > floor(0.5 * 4) = 2 -> doublon
    doublon, index, communs = selection.est_doublon([1, 2, 3, 9], [precedente])
    assert doublon is True and index == 0 and communs == 3
    # 2 en commun sur 4 : 2 <= 2 -> accepté
    doublon, index, _ = selection.est_doublon([1, 2, 10, 11], [precedente])
    assert doublon is False and index is None
    assert selection.capteurs_communs([1, 2, 10, 11], precedente) == 2


def test_doublon_independant_de_l_ordre(config_par_defaut):
    doublon, _, _ = selection.est_doublon([4, 3, 1, 2], [[1, 2, 3, 4]])
    assert doublon is True


def test_generation_de_combinaisons_distinctes(config_par_defaut):
    donnees = jeu_artificiel(n_capteurs=40, n_bandes=4, n_excitations=3)
    resume = data_io.valider_mesures(donnees)
    niveaux = {excitation: data_io.donnees_accel(donnees, excitation)[2]
               for excitation in resume["excitations"]}
    _, coordonnees, _ = data_io.donnees_accel(donnees,
                                              resume["excitations"][0])
    resultats = selection.generer_combinaisons_finales(
        resume["excitations"], niveaux, coordonnees, list(range(40)), 5, 3,
        random.Random(11), noms_capteurs=resume["capteurs"],
    )
    assert len(resultats) == 3
    for description in resultats:
        assert len(set(description["combinaison"])) == \
            len(description["combinaison"])
        assert set(description["initiale"]) <= set(description["combinaison"])
    for premier in range(len(resultats)):
        for second in range(premier + 1, len(resultats)):
            combinaison_a = set(resultats[premier]["combinaison"])
            combinaison_b = set(resultats[second]["combinaison"])
            limite = math.floor(config.CapteursCommuns
                                * min(len(combinaison_a), len(combinaison_b)))
            assert len(combinaison_a & combinaison_b) <= limite


def test_arret_propre_si_trop_de_tests_demandes(config_par_defaut,
                                                monkeypatch):
    # 10 capteurs, combinaisons de 5 : impossible d'obtenir 10 combinaisons
    # partageant au plus 2 capteurs deux à deux.
    monkeypatch.setattr(config, "MAX_TENTATIVES_PAR_TEST", 20)
    donnees = jeu_artificiel(n_capteurs=10, n_bandes=3, n_excitations=1)
    resume = data_io.valider_mesures(donnees)
    niveaux = {excitation: data_io.donnees_accel(donnees, excitation)[2]
               for excitation in resume["excitations"]}
    _, coordonnees, _ = data_io.donnees_accel(donnees,
                                              resume["excitations"][0])
    with pytest.raises(selection.SelectionImpossible) as erreur:
        selection.generer_combinaisons_finales(
            resume["excitations"], niveaux, coordonnees, list(range(10)), 5,
            10, random.Random(3),
        )
    assert "Nb_Test" in str(erreur.value)


def test_graine_reproductible(config_par_defaut, monkeypatch):
    monkeypatch.setattr(config, "RANDOM_SEED", 777)
    generateur_a, graine_a = selection.creer_generateur()
    generateur_b, graine_b = selection.creer_generateur()
    assert graine_a == graine_b == 777
    coordonnees = [[float(i), 0.0, 0.0] for i in range(12)]
    assert selection.selection_initiale(coordonnees, list(range(12)), 4,
                                        generateur_a) == \
        selection.selection_initiale(coordonnees, list(range(12)), 4,
                                     generateur_b)
    monkeypatch.setattr(config, "RANDOM_SEED", None)
    _, graine_c = selection.creer_generateur()
    assert isinstance(graine_c, int)


# ---------------------------------------------------------------------------
# 4. Chaîne complète
# ---------------------------------------------------------------------------

def _executer(tmp_path, monkeypatch, methode, sigma_cible=None,
              n_capteurs=40, nb_tests=3):
    donnees = jeu_artificiel(n_capteurs=n_capteurs, n_bandes=5,
                             n_excitations=3, sigma_cible=sigma_cible)
    monkeypatch.chdir(tmp_path)
    ecrire_jeu(tmp_path, donnees, "mesures.json")
    monkeypatch.setattr(config, "FICHIER_ENTREE", "mesures.json")
    monkeypatch.setattr(config, "Nb_Test", nb_tests)
    if methode == 1:
        chemin_sortie, cle, n_init, facteur = ("DataISO7849_1.json",
                                               "DataISO7849_1", 5, False)
    else:
        chemin_sortie, cle, n_init, facteur = ("DataISO7849_2.json",
                                               "DataISO7849_2", 10, True)
    monkeypatch.setattr(config, "FICHIER_SORTIE_ISO1", "DataISO7849_1.json")
    monkeypatch.setattr(config, "FICHIER_SORTIE_ISO2", "DataISO7849_2.json")
    chemin, tests, metadonnees = pipeline.executer_methode(
        "ISO7849_%d" % methode, n_init, cle, chemin_sortie, facteur,
        journal=lambda texte: None,
    )
    return donnees, chemin, tests, metadonnees


def test_chaine_complete_iso1(tmp_path, monkeypatch, config_par_defaut):
    donnees, chemin, tests, metadonnees = _executer(tmp_path, monkeypatch, 1)

    assert os.path.isfile(chemin)
    assert sorted(tests) == ["TEST1", "TEST2", "TEST3"]
    terme = calculs.terme_surface_impedance()

    for nom_test, bloc_test in tests.items():
        assert data_io.lister_excitations(bloc_test) == [
            "EXCITATION1", "EXCITATION2", "EXCITATION3"
        ]
        capteurs_reference = None
        for excitation, bloc in bloc_test.items():
            # Champs attendus, et aucun facteur de rayonnement en ISO 7849-1
            assert set(bloc) == {
                "frq_3rdOctave", "Data_3rdOctave_Acou", "Data_GlobalLevel_Acou",
                "Accel_name", "Accel_coordinates", "Data_3rdOctave_Vel",
                "Data_3rdOctaveMean_Vel", "Data_3rdOctave_Vib",
                "Data_GlobalLevel_Vib",
            }
            # Combinaison figée : identique pour toutes les excitations du test
            if capteurs_reference is None:
                capteurs_reference = bloc["Accel_name"]
            assert bloc["Accel_name"] == capteurs_reference
            assert len(bloc["Accel_coordinates"]) == len(bloc["Accel_name"])
            assert len(bloc["Data_3rdOctave_Vel"]) == len(bloc["Accel_name"])

            # Données acoustiques recopiées sans modification
            source = donnees[excitation]["Micro"]
            assert bloc["Data_3rdOctave_Acou"] == source["Data_3rdOctave_Lw"]
            assert bloc["Data_GlobalLevel_Acou"] == source["Data_GlobalLevel_Lw"]

            # Moyenne recalculée, jamais reprise du fichier source
            assert all(valeur > -100.0 for valeur in bloc["Data_3rdOctaveMean_Vel"])
            attendue = [
                calculs.moyenne_energetique(
                    [ligne[bande] for ligne in bloc["Data_3rdOctave_Vel"]]
                )
                for bande in range(len(bloc["frq_3rdOctave"]))
            ]
            assert bloc["Data_3rdOctaveMean_Vel"] == pytest.approx(attendue)
            assert bloc["Data_3rdOctave_Vib"] == pytest.approx(
                [valeur + terme for valeur in attendue]
            )
            assert bloc["Data_GlobalLevel_Vib"] == pytest.approx(
                calculs.niveau_global(bloc["Data_3rdOctave_Vib"])
            )

    assert metadonnees["nb_tests"] == 3
    assert metadonnees["nb_excitations"] == 3
    assert len(metadonnees["tests"]) == 3


def test_chaine_complete_iso2(tmp_path, monkeypatch, config_par_defaut):
    sigma = [0.5, 1.0, 2.0, 3.0, 0.75]
    donnees, chemin, tests, metadonnees = _executer(
        tmp_path, monkeypatch, 2, sigma_cible=sigma, n_capteurs=60
    )

    facteur = metadonnees["facteur_rayonnement"]["valeur_utilisee"]
    assert facteur == pytest.approx(sigma)

    for bloc_test in tests.values():
        for bloc in bloc_test.values():
            assert "Data_3rdOctave_Radiation_Factor" in bloc
            # Même facteur pour tous les tests et toutes les excitations
            assert bloc["Data_3rdOctave_Radiation_Factor"] == \
                pytest.approx(sigma)
            attendu = calculs.spectre_vib_iso2(
                bloc["Data_3rdOctaveMean_Vel"], sigma
            )
            assert bloc["Data_3rdOctave_Vib"] == pytest.approx(attendu)

    # Combinaison initiale de 10 capteurs pour ISO 7849-2
    assert metadonnees["n_capteurs_initiaux"] == 10
    for resume_test in metadonnees["tests"]:
        assert len(resume_test["capteurs_initiaux"]) == 10


def test_chaine_respecte_les_capteurs_exclus(tmp_path, monkeypatch,
                                             config_par_defaut):
    monkeypatch.setattr(config, "CAPTEURS_EXCLUS", ["Accel01", "Accel02"])
    _, _, tests, metadonnees = _executer(tmp_path, monkeypatch, 1)
    for bloc_test in tests.values():
        for bloc in bloc_test.values():
            assert "Accel01" not in bloc["Accel_name"]
            assert "Accel02" not in bloc["Accel_name"]
    assert metadonnees["nb_capteurs_utilisables"] == 38


def test_chaine_arrete_si_critere_inatteignable(tmp_path, monkeypatch,
                                                config_par_defaut):
    # Dispersion de 60 dB pour 12 capteurs : le critère est hors d'atteinte.
    donnees = jeu_artificiel(n_capteurs=12, n_bandes=3, n_excitations=1,
                             dispersion_db=60.0)
    monkeypatch.chdir(tmp_path)
    ecrire_jeu(tmp_path, donnees, "mesures.json")
    monkeypatch.setattr(config, "FICHIER_ENTREE", "mesures.json")
    with pytest.raises(selection.SelectionImpossible) as erreur:
        pipeline.executer_methode("ISO7849_1", 5, "DataISO7849_1",
                                  "sortie.json", False,
                                  journal=lambda texte: None)
    assert "inatteignable" in str(erreur.value)
    assert not os.path.isfile(os.path.join(str(tmp_path), "sortie.json"))


def test_fichier_source_non_modifie(tmp_path, monkeypatch, config_par_defaut):
    donnees = jeu_artificiel(n_capteurs=40, n_bandes=4, n_excitations=2)
    monkeypatch.chdir(tmp_path)
    chemin_source = ecrire_jeu(tmp_path, donnees, "mesures.json")
    with open(chemin_source, "rb") as flux:
        avant = flux.read()
    monkeypatch.setattr(config, "FICHIER_ENTREE", "mesures.json")
    monkeypatch.setattr(config, "Nb_Test", 2)
    pipeline.executer_methode("ISO7849_1", 5, "DataISO7849_1",
                              "DataISO7849_1.json", False,
                              journal=lambda texte: None)
    with open(chemin_source, "rb") as flux:
        assert flux.read() == avant


def test_relecture_des_resultats(tmp_path, monkeypatch, config_par_defaut):
    _, chemin, _, _ = _executer(tmp_path, monkeypatch, 1, nb_tests=2)
    cle_racine, tests, metadonnees = data_io.lire_resultats(chemin)
    assert cle_racine == "DataISO7849_1"
    assert data_io.trier_tests(tests) == ["TEST1", "TEST2"]
    assert metadonnees["methode"] == "ISO7849_1"


# ---------------------------------------------------------------------------
# 5. Figures
# ---------------------------------------------------------------------------

def test_figures_produisent_les_png(tmp_path, monkeypatch, config_par_defaut):
    _, chemin, _, _ = _executer(tmp_path, monkeypatch, 1, nb_tests=2)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as pyplot
    import figures

    ecrits = figures.tracer_fichier(
        chemin, pyplot, dossier_figures=os.path.join(str(tmp_path), "figures"),
        enregistrer=True, journal=lambda texte: None,
    )
    pyplot.close("all")
    # 3 excitations x (spectres + globaux)
    assert len(ecrits) == 6
    for fichier in ecrits:
        assert os.path.isfile(fichier) and os.path.getsize(fichier) > 1000
    noms = [os.path.basename(fichier) for fichier in ecrits]
    assert "ISO7849-1_EXCITATION1_spectres.png" in noms
    assert "ISO7849-1_EXCITATION3_globaux.png" in noms
