# -*- coding: utf-8 -*-
"""Enchaînement de la méthode Cristofori_Mucchi : phases 1 et 2, résultats.

Pour chaque valeur de n de N_CAPTEUR_COMBINAISON (ordre croissant) et pour
chaque test (Nb_Test par valeur de n), une NOUVELLE sélection de capteurs est
tirée (phase 1, identique à ISO 7849-2 avec favorisation spatiale), puis la
phase 2 évalue les C(p, n) combinaisons. Le tirage est recommencé lorsque :

* le critère max/min est inatteignable avec les capteurs disponibles ;
* la sélection est trop proche d'une sélection déjà retenue (CapteursCommuns,
  pour une même valeur de n) ;
* la sélection contient moins de n capteurs, ou plus de MAX_COMBINAISONS
  combinaisons ;
* l'ensemble k' (plusieurs excitations) ou k'_m (une excitation) est vide
  (limité à MAX_RELANCES_K_PRIME relances par test).
"""

from __future__ import annotations

import math

import numpy as np

import calculs
import config
import data_io
import selection_capteurs as selection

LARGEUR = 64


class ErreurConfiguration(Exception):
    """Paramètre de config.py invalide."""


# ---------------------------------------------------------------------------
# Utilitaires d'affichage
# ---------------------------------------------------------------------------

def titre(texte, journal=print):
    journal("=" * LARGEUR)
    journal(texte)
    journal("=" * LARGEUR)


def _noms(noms_capteurs, indices):
    return "(" + ", ".join(noms_capteurs[i] for i in indices) + ")"


# ---------------------------------------------------------------------------
# Préparation
# ---------------------------------------------------------------------------

def valeurs_n():
    """Valeurs de n validées, triées par ordre croissant, sans doublon."""
    brut = config.N_CAPTEUR_COMBINAISON
    if not isinstance(brut, (list, tuple)) or not brut:
        raise ErreurConfiguration("N_CAPTEUR_COMBINAISON doit être une liste "
                                  "non vide d'entiers (ex. [2] ou [2, 4]).")
    valeurs = []
    for n in brut:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ErreurConfiguration(
                "N_CAPTEUR_COMBINAISON : entier >= 1 attendu, reçu %r." % (n,))
        valeurs.append(n)
    return sorted(set(valeurs))


def controler_configuration():
    """Contrôles généraux des paramètres numériques."""
    if config.Nb_Test < 1:
        raise ErreurConfiguration("Nb_Test doit être >= 1.")
    if config.TARGET_VALUE <= 0:
        raise ErreurConfiguration("TARGET_VALUE doit être > 0.")
    if config.MAX_RELANCES_K_PRIME < 0 or config.MAX_TENTATIVES_PAR_TEST < 1:
        raise ErreurConfiguration("MAX_RELANCES_K_PRIME >= 0 et "
                                  "MAX_TENTATIVES_PAR_TEST >= 1 attendus.")
    if config.MAX_COMBINAISONS < 1:
        raise ErreurConfiguration("MAX_COMBINAISONS doit être >= 1.")
    if config.INCERTITUDE_FACTEUR_ELARGISSEMENT <= 0:
        raise ErreurConfiguration("INCERTITUDE_FACTEUR_ELARGISSEMENT doit être > 0.")
    for plage in config.INCERTITUDE_TERMES_BANDES:
        if len(plage) != 3 or plage[0] > plage[1] or plage[2] < 0:
            raise ErreurConfiguration(
                "INCERTITUDE_TERMES_BANDES : (f_min, f_max, s_r0) avec "
                "f_min <= f_max et s_r0 >= 0 attendu, reçu %r." % (plage,))
    calculs.terme_surface_impedance()


def preparer(journal=print):
    """Lit et valide les données ; renvoie le contexte de calcul."""
    controler_configuration()
    donnees = data_io.lire_mesures()
    excitations = data_io.excitations_a_traiter(donnees)
    resume = data_io.valider_mesures(donnees, excitations)
    noms_capteurs = resume["capteurs"]
    frequences = resume["frequences"]
    disponibles = data_io.indices_capteurs_disponibles(noms_capteurs)

    n_init = (int(config.N_CAPTEURS_INIT_ISO2)
              if config.N_CAPTEURS_INIT_ISO2 is not None
              else calculs.positions_initiales_table1())
    if len(disponibles) < n_init:
        raise data_io.ErreurDonnees(
            "Après exclusion de %d capteur(s) il reste %d capteurs, la "
            "combinaison initiale en demande %d."
            % (len(config.CAPTEURS_EXCLUS), len(disponibles), n_init))

    _, coordonnees, _ = data_io.donnees_accel(donnees, excitations[0])
    niveaux_vel, acou = {}, {}
    for exc in excitations:
        _, _, niveaux_vel[exc] = data_io.donnees_accel(donnees, exc)
        lac_j, lac_glob, runs = data_io.donnees_micro(donnees, exc)
        acou[exc] = {"lac_j": np.array(lac_j), "lac": lac_glob,
                     "runs": runs}

    ns = valeurs_n()
    mono = len(excitations) == 1

    titre("Méthode Cristofori_Mucchi", journal)
    journal("Fichier source           : %s" % config.FICHIER_ENTREE)
    journal("Excitations traitées     : %d (%s)%s"
            % (len(excitations), ", ".join(excitations),
               "  [une seule : cas k'_m]" if mono else ""))
    if config.EXCITATIONS_A_EXCLURE:
        journal("Excitations exclues      : %s" % config.EXCITATIONS_A_EXCLURE)
    journal("Capteurs dans le fichier : %d, utilisables : %d"
            % (len(noms_capteurs), len(disponibles)))
    journal("Tiers d'octave           : %d (%g Hz à %g Hz)"
            % (len(frequences), frequences[0], frequences[-1]))
    journal("Valeurs de n             : %s ; Nb_Test = %d par valeur de n"
            % (ns, config.Nb_Test))
    journal("Capteurs initiaux (ph.1) : %d ; critère max/min : %s"
            % (n_init, ("écart_j < %g dB (SEUIL_ECART_DB)" % config.SEUIL_ECART_DB)
               if config.SEUIL_ECART_DB is not None
               else "écart_j < %g x n" % config.FACTEUR_CRITERE_ISO2))
    journal("TARGET_VALUE (TV)        : %g dB" % config.TARGET_VALUE)
    journal("Terme 10log(S/S0)+10log(ZC/ZC0) = %.4f dB"
            % calculs.terme_surface_impedance())

    # Cohérence entre les deux sources de Lac (information, pas de correction)
    for exc in excitations:
        lac_calc = float(calculs.niveau_global(acou[exc]["lac_j"]))
        journal("  %s : Lac (GlobalLevelMean_Lw) = %.3f dB ; somme de "
                "3rdOctaveMean_Lw = %.3f dB ; %d runs"
                % (exc, acou[exc]["lac"], lac_calc, len(acou[exc]["runs"])))

    return {
        "donnees": donnees, "excitations": excitations, "mono": mono,
        "noms_capteurs": noms_capteurs, "frequences": frequences,
        "disponibles": disponibles, "coordonnees": coordonnees,
        "niveaux_vel": niveaux_vel, "acou": acou, "n_init": n_init, "ns": ns,
    }


def controler_faisabilite(ctx, journal=print):
    """Diagnostic préalable du critère max/min (identique ISO 7849-2)."""
    facteur = config.FACTEUR_CRITERE_ISO2
    diag = selection.diagnostic_faisabilite(
        ctx["niveaux_vel"], ctx["disponibles"], facteur=facteur)
    journal("")
    journal("--- Diagnostic préalable de la phase 1 ---")
    journal("Écart max/min maximal avec les %d capteurs utilisables : %.1f dB"
            % (diag["n_capteurs_disponibles"], diag["ecart_maximal"]))
    if not diag["faisable"]:
        ex = diag["bandes_bloquantes"][0]
        raise selection.SelectionImpossible(
            "Le critère max/min ne peut être satisfait par AUCUNE combinaison : "
            "avec les %d capteurs, l'écart reste >= %.1f sur %d bande(s), par "
            "exemple %s bande %d (%.1f dB). Exclure des capteurs aberrants "
            "(CAPTEURS_EXCLUS), vérifier les niveaux, ou fixer SEUIL_ECART_DB."
            % (diag["n_capteurs_disponibles"], diag["seuil"],
               len(diag["bandes_bloquantes"]), ex[0], ex[1] + 1, ex[2]))
    if selection.mode_seuil_fixe():
        est = selection.taux_acceptation_initiale(
            ctx["niveaux_vel"], ctx["coordonnees"], ctx["disponibles"],
            ctx["n_init"], selection.creer_generateur(graine=0)[0],
            facteur=facteur)
        journal("Tirages initiaux acceptés avec le seuil fixe : %.0f %% "
                "(meilleur écart %.1f dB)" % (100 * est["taux"],
                                              est["meilleur_ecart"]))
        if est["taux"] == 0.0:
            raise selection.SelectionImpossible(
                "Aucun tirage de %d capteurs ne respecte SEUIL_ECART_DB = %.1f "
                "dB (meilleur écart %.1f dB)."
                % (ctx["n_init"], diag["seuil"], est["meilleur_ecart"]))
    journal("Critère max/min atteignable : oui")
    return diag


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

def phase2(ctx, selection_idx, n, journal=print):
    """Phase 2 pour une sélection de p capteurs et un n donné.

    Renvoie un dictionnaire de résultats ; la clé "vide" vaut True lorsque
    l'ensemble k' (ou k'_m) est vide.
    """
    excitations = ctx["excitations"]
    p = len(selection_idx)
    combis = calculs.generer_combinaisons(p, n)
    k = len(combis)
    terme = calculs.terme_surface_impedance()
    tv = config.TARGET_VALUE

    par_exc = {}
    masques = {}
    for exc in excitations:
        niveaux_sel = [ctx["niveaux_vel"][exc][i] for i in selection_idx]
        ev = calculs.evaluer_excitation(
            niveaux_sel, combis, ctx["acou"][exc]["lac_j"],
            ctx["acou"][exc]["lac"], terme)
        masques[exc] = ev["delta"] < tv
        par_exc[exc] = ev
        journal("    %s : %d/%d combinaisons avec delta_mk < %g dB (k'_m)"
                % (exc, int(masques[exc].sum()), k, tv))

    commun = np.logical_and.reduce([masques[e] for e in excitations])
    res = {"p": p, "n": n, "K": k, "combis": combis, "par_exc": par_exc,
           "masques": masques, "vide": False}

    if ctx["mono"]:
        exc = excitations[0]
        idx = np.flatnonzero(masques[exc])
        res["k_prime_m"] = {exc: idx}
        if len(idx) == 0:
            res["vide"] = True
            return res
        ss = calculs.indice_similarite(ctx["acou"][exc]["lac_j"],
                                       par_exc[exc]["Lvib_j"][idx])
        res["ss_m"] = {exc: ss}
        res["k_2prime"] = int(idx[int(np.argmin(ss))])
        res["ss_best"] = float(ss.min())
    else:
        res["k_prime_m"] = {e: np.flatnonzero(masques[e]) for e in excitations}
        idx = np.flatnonzero(commun)
        res["k_prime"] = idx
        journal("    k' (combinaisons communes à toutes les excitations) : %d"
                % len(idx))
        if len(idx) == 0:
            res["vide"] = True
            return res
        ss_m = {e: calculs.indice_similarite(ctx["acou"][e]["lac_j"],
                                             par_exc[e]["Lvib_j"][idx])
                for e in excitations}
        total = np.sum([ss_m[e] for e in excitations], axis=0)
        res["ss_m"] = ss_m
        res["ss_total"] = total
        res["k_2prime"] = int(idx[int(np.argmin(total))])
        res["ss_best"] = float(total.min())
    return res


# ---------------------------------------------------------------------------
# Boucle des tests
# ---------------------------------------------------------------------------

def executer_test(ctx, n, numero_test, retenues, generateur, journal=print):
    """Un test : sélection (phase 1) + phase 2, avec relances.

    Renvoie (description de la sélection, résultats de phase 2).
    """
    nom_test = "TEST%d" % numero_test
    noms = ctx["noms_capteurs"]
    facteur = config.FACTEUR_CRITERE_ISO2
    tentative = 0
    relances = 0
    while True:
        tentative += 1
        if tentative > config.MAX_TENTATIVES_PAR_TEST:
            raise selection.SelectionImpossible(
                "n=%d, %s : %d tentatives de sélection infructueuses "
                "(MAX_TENTATIVES_PAR_TEST). Pistes : réduire Nb_Test ou n, "
                "augmenter CapteursCommuns, TARGET_VALUE ou "
                "MAX_TENTATIVES_PAR_TEST, réduire CAPTEURS_EXCLUS."
                % (n, nom_test, tentative - 1))
        try:
            comb, initiale, ajouts = selection.construire_combinaison_finale(
                ctx["excitations"], ctx["niveaux_vel"], ctx["coordonnees"],
                ctx["disponibles"], ctx["n_init"], generateur,
                journal=journal, noms_capteurs=noms, facteur=facteur)
        except selection.CritereInatteignable as err:
            journal("  Critère max/min non satisfait avec tous les capteurs "
                    "(%s) -> nouveau tirage (tentative %d)." % (err, tentative + 1))
            continue

        doublon, ref, communs = selection.est_doublon(comb, retenues)
        if doublon:
            journal("  Doublon : %d capteurs communs avec une sélection déjà "
                    "retenue (CapteursCommuns = %g) -> nouveau tirage "
                    "(tentative %d)." % (communs, config.CapteursCommuns,
                                         tentative + 1))
            continue

        p = len(comb)
        journal("  Sélection finale : p = %d capteurs : %s"
                % (p, ", ".join(noms[i] for i in comb)))
        if p < n:
            journal("  p = %d < n = %d : combinaisons impossibles -> nouveau "
                    "tirage (tentative %d)." % (p, n, tentative + 1))
            continue
        nb = calculs.nombre_combinaisons(p, n)
        if nb > config.MAX_COMBINAISONS:
            journal("  C(%d,%d) = %d > MAX_COMBINAISONS (%d) -> nouveau tirage "
                    "(tentative %d)." % (p, n, nb, config.MAX_COMBINAISONS,
                                         tentative + 1))
            continue

        journal("  Phase 2 : C(%d,%d) = %d combinaisons" % (p, n, nb))
        sel_tri = sorted(comb)
        res = phase2(ctx, sel_tri, n, journal=journal)
        if res["vide"]:
            relances += 1
            ens = "k'_m" if ctx["mono"] else "k'"
            if relances > config.MAX_RELANCES_K_PRIME:
                raise selection.SelectionImpossible(
                    "n=%d, %s : l'ensemble %s est vide après %d relances "
                    "(MAX_RELANCES_K_PRIME = %d). Aucune combinaison de %d "
                    "capteurs ne vérifie delta_mk < TARGET_VALUE (%g dB) %s. "
                    "Augmenter TARGET_VALUE ou MAX_RELANCES_K_PRIME, ou "
                    "changer n."
                    % (n, nom_test, ens, relances - 1,
                       config.MAX_RELANCES_K_PRIME, n, config.TARGET_VALUE,
                       "pour l'excitation" if ctx["mono"]
                       else "simultanément pour toutes les excitations"))
            journal("  Ensemble %s vide -> relance de la sélection (relance "
                    "%d/%d)." % (ens, relances, config.MAX_RELANCES_K_PRIME))
            continue

        retenues.append(list(comb))
        res["selection"] = sel_tri
        description = {
            "selection": sel_tri, "initiale": list(initiale),
            "ajouts": ajouts, "tentatives": tentative, "relances": relances,
        }
        return description, res


# ---------------------------------------------------------------------------
# Construction du JSON
# ---------------------------------------------------------------------------

def _liste(a):
    return np.asarray(a).tolist()


def _bloc_valeurs(ctx, res, exc, idx, avec_u, u_lac, ss_m=None):
    """Bloc de grandeurs d'une excitation pour les combinaisons `idx`."""
    ev = res["par_exc"][exc]
    bloc = {
        "Data_3rdOctaveMean_Vel": _liste(ev["Lv_j"][idx]),
        "Data_3rdOctave_Vib": _liste(ev["Lvib_j"][idx]),
        "Data_GlobalLevel_Vib": _liste(ev["Lvib"][idx]),
        "Data_Delta_mk": _liste(ev["delta"][idx]),
    }
    if ss_m is not None:
        bloc["Spectral_Similarity_m"] = _liste(ss_m)
    bloc["Data_3rdOctave_Radiation_Factor"] = _liste(ev["sigma"][idx])
    if avec_u:
        bloc["Data_3rdOctave_Radiation_Factor_Uncertainty"] = _liste(
            calculs.incertitude_facteur_rayonnement(ev["sigma"][idx],
                                                    u_lac[exc][None, :]))
    return bloc


def construire_test(ctx, res, description, u_lac):
    """Bloc JSON d'un test (structure des fichiers exemples)."""
    noms = ctx["noms_capteurs"]
    exc_list = ctx["excitations"]
    mono = ctx["mono"]
    avec_u = bool(config.INCERTITUDES_DANS_RESULTATS)
    sel = res["selection"]
    combis = res["combis"]

    def noms_combis(idx):
        return [[noms[sel[c]] for c in combis[i]] for i in idx]

    tous = np.arange(res["K"])
    test = {}

    # Data_k
    data_k = {}
    if mono:
        exc = exc_list[0]
        data_k[exc] = {"k_ensemble": noms_combis(tous)}
        data_k[exc].update(_bloc_valeurs(ctx, res, exc, tous, avec_u, u_lac))
    else:
        data_k["k_ensemble"] = noms_combis(tous)
        for exc in exc_list:
            data_k[exc] = _bloc_valeurs(ctx, res, exc, tous, avec_u, u_lac)
    test["Data_k"] = data_k

    # Data_k_prime_m
    dkpm = {}
    for exc in exc_list:
        idx = res["k_prime_m"][exc]
        bloc = {"k_prime_m_ensemble": noms_combis(idx)}
        ss = None
        if mono:
            ss = res["ss_m"][exc]
        bloc.update(_bloc_valeurs(ctx, res, exc, idx, avec_u, u_lac, ss_m=ss))
        dkpm[exc] = bloc
    test["Data_k_prime_m"] = dkpm

    meilleur = np.array([res["k_2prime"]])
    if mono:
        exc = exc_list[0]
        pos = int(np.flatnonzero(res["k_prime_m"][exc] == res["k_2prime"])[0])
        bloc = {"k_2prime_ensemble": noms_combis(meilleur)[0]}
        bloc[exc] = _bloc_valeurs(ctx, res, exc, meilleur, avec_u, u_lac,
                                  ss_m=res["ss_m"][exc][[pos]])
        for cle, val in list(bloc[exc].items()):
            bloc[exc][cle] = val[0]
        test["Data_k_2prime"] = bloc
    else:
        idx = res["k_prime"]
        dkp = {"k_prime_ensemble": noms_combis(idx),
               "Spectral_Similarity": _liste(res["ss_total"])}
        for exc in exc_list:
            dkp[exc] = _bloc_valeurs(ctx, res, exc, idx, avec_u, u_lac,
                                     ss_m=res["ss_m"][exc])
        test["Data_k_prime"] = dkp

        pos = int(np.flatnonzero(idx == res["k_2prime"])[0])
        bloc = {"k_2prime_ensemble": noms_combis(meilleur)[0],
                "Spectral_Similarity": float(res["ss_total"][pos])}
        sigmas, incs = [], []
        for exc in exc_list:
            b = _bloc_valeurs(ctx, res, exc, meilleur, avec_u, u_lac,
                              ss_m=res["ss_m"][exc][[pos]])
            bloc[exc] = {cle: val[0] for cle, val in b.items()}
            sigmas.append(res["par_exc"][exc]["sigma"][res["k_2prime"]])
            incs.append(calculs.incertitude_facteur_rayonnement(
                sigmas[-1], u_lac[exc]))
        moy, u_moy = calculs.moyenne_facteurs_excitations(
            sigmas, incs if avec_u else None)
        bloc["Data_3rdOctave_Radiation_Factor_Moyen"] = _liste(moy)
        if avec_u:
            bloc["Data_3rdOctave_Radiation_Factor_Moyen_Uncertainty"] = _liste(u_moy)
        test["Data_k_2prime"] = bloc

    # Données d'entrée utilisées
    indices = ctx["disponibles"]
    accel = {"Accel_name": [noms[i] for i in indices],
             "Accel_coordinates": [ctx["coordonnees"][i] for i in indices]}
    acou = {"frq_3rdOctave": list(ctx["frequences"])}
    for exc in exc_list:
        accel[exc] = {"Data_3rdOctave_Vel": [ctx["niveaux_vel"][exc][i]
                                             for i in indices]}
        acou[exc] = {"Data_3rdOctave_Acou": _liste(ctx["acou"][exc]["lac_j"])}
        if avec_u:
            acou[exc]["Data_3rdOctave_Acou_Uncertainty"] = _liste(u_lac[exc])
        acou[exc]["Data_GlobalLevel_Acou"] = ctx["acou"][exc]["lac"]
    test["Data_Accel"] = accel
    test["Data_Acou"] = acou

    test["Data_Selection"] = {
        "p": res["p"], "n": res["n"], "nb_combinaisons_k": res["K"],
        "selection_finale": [noms[i] for i in sel],
        "combinaison_initiale": [noms[i] for i in description["initiale"]],
        "capteurs_ajoutes_par_excitation": {
            e: [noms[i] for i in a] for e, a in description["ajouts"].items()},
        "tentatives": description["tentatives"],
        "relances_k_prime": description["relances"],
    }
    return test


def calculer_incertitudes_lac(ctx, journal=print):
    """u(Lac_j) par excitation (vide si INCERTITUDES_DANS_RESULTATS est faux).

    Les figures relisent le fichier de résultats : sans incertitudes enregistrées,
    elles ne peuvent pas être tracées (message explicite dans figures.py).
    """
    u = {}
    if not config.INCERTITUDES_DANS_RESULTATS:
        return u
    journal("")
    journal("--- Incertitudes sur Lac_j ---")
    for exc in ctx["excitations"]:
        runs = ctx["acou"][exc]["runs"]
        u[exc] = calculs.incertitude_lac(runs, ctx["frequences"])
        ecart = np.max(np.abs(calculs.moyenne_energetique_runs(runs)
                              - ctx["acou"][exc]["lac_j"]))
        journal("  %s : R = %d runs, u(Lac_j) = %s dB ; écart max entre la "
                "moyenne énergétique des runs et Data_3rdOctaveMean_Lw : "
                "%.2e dB"
                % (exc, len(runs),
                   ", ".join("%.2f" % v for v in u[exc]), ecart))
    return u


def executer(journal=print):
    """Exécute la méthode complète et renvoie le dictionnaire de résultats."""
    ctx = preparer(journal)
    diag = controler_faisabilite(ctx, journal)
    u_lac = calculer_incertitudes_lac(ctx, journal)

    generateur, graine = selection.creer_generateur()
    journal("Graine aléatoire utilisée : %d%s" % (
        graine, "" if config.RANDOM_SEED is not None
        else " (tirée au hasard, recopiable dans RANDOM_SEED)"))

    racine = ("DataCristofori_EXC%d" % data_io.numero_excitation(
        ctx["excitations"][0]) if ctx["mono"] else "DataCristofori")
    contenu_racine = {}
    resumes = []

    for n in ctx["ns"]:
        titre("n = %d (%d test(s))" % (n, config.Nb_Test), journal)
        bloc_n = {}
        retenues = []
        for numero in range(1, config.Nb_Test + 1):
            journal("")
            journal("TEST%d (n = %d)" % (numero, n))
            description, res = executer_test(ctx, n, numero, retenues,
                                             generateur, journal)
            noms = ctx["noms_capteurs"]
            sel = res["selection"]
            best = res["combis"][res["k_2prime"]]
            journal("  >>> k_2prime = %s ; Spectral_Similarity = %.5f"
                    % (_noms(noms, [sel[c] for c in best]), res["ss_best"]))
            for exc in ctx["excitations"]:
                ev = res["par_exc"][exc]
                journal("      %s : Lvib = %.2f dB, Lac = %.2f dB, "
                        "delta_mk = %.3f dB"
                        % (exc, ev["Lvib"][res["k_2prime"]],
                           ctx["acou"][exc]["lac"],
                           ev["delta"][res["k_2prime"]]))
            bloc_n["TEST%d" % numero] = construire_test(
                ctx, res, description, u_lac)
            resumes.append({
                "n": n, "test": "TEST%d" % numero, "p": res["p"],
                "k": res["K"],
                "k_prime_m": {e: int(len(i)) for e, i in res["k_prime_m"].items()},
                "k_prime": (int(len(res["k_prime"])) if not ctx["mono"] else None),
                "k_2prime": [noms[sel[c]] for c in best],
                "Spectral_Similarity": res["ss_best"],
                "tentatives": description["tentatives"],
                "relances_k_prime": description["relances"],
            })
        contenu_racine["n_equal_%d" % n] = bloc_n

    metadata = {
        "methode": "Cristofori_Mucchi",
        "date_execution": data_io.horodatage(),
        "fichier_entree": config.FICHIER_ENTREE,
        "mode": "une excitation" if ctx["mono"] else "plusieurs excitations",
        "excitations_traitees": ctx["excitations"],
        "excitations_exclues": list(config.EXCITATIONS_A_EXCLURE),
        "nb_capteurs_fichier": len(ctx["noms_capteurs"]),
        "nb_capteurs_utilisables": len(ctx["disponibles"]),
        "capteurs_exclus": list(config.CAPTEURS_EXCLUS),
        "valeurs_n": ctx["ns"],
        "nb_tests_par_n": config.Nb_Test,
        "n_capteurs_initiaux": ctx["n_init"],
        "graine_aleatoire": graine,
        "terme_surface_impedance_dB": calculs.terme_surface_impedance(),
        "ecart_max_min_tous_capteurs_dB": diag["ecart_maximal"],
        "cles_utilisees": {
            "Lv_i_j": "Accel.Data_3rdOctave_Vel",
            "Lac_j": "Micro.Data_3rdOctaveMean_Lw",
            "Lac": "Micro.Data_GlobalLevelMean_Lw",
            "incertitudes": "Micro.Data_3rdOctave_Lw (par run)",
        },
        "parametres": data_io.parametres_config(),
        "resume_tests": resumes,
    }
    return {racine: contenu_racine, "Metadata": metadata}
