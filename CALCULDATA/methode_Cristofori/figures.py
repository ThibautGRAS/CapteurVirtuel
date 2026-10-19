# -*- coding: utf-8 -*-
"""Figures de la méthode Cristofori_Mucchi.

Les figures sont tracées à partir du fichier de résultats JSON (ou du
dictionnaire qui vient d'être calculé) :

    python figures.py                      relit config.FICHIER_SORTIE
    python figures.py --fichier autre.json
    python figures.py --interactif         affiche aussi les fenêtres

Arborescence : <DOSSIER_FIGURES>/n_equal_x/TESTX/<type>_n<x>_TESTX_<exc>.png

Quatre groupes activables dans config.py : combinaison finale (k_2prime), k' ou
k'_m, indices de similarité, facteur de rayonnement. Tous les niveaux
acoustiques sont tracés en rouge. Une figure impossible faute de données est
signalée par un message et le traitement continue.
"""

from __future__ import annotations

import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib

import config
import data_io

if not config.FIGURES_INTERACTIF and "--interactif" not in sys.argv:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROUGE = config.FIGURES_COULEUR_ACOU
MARQUEURS = ["o", "s", "^", "D", "v", "P", "X", "*", "h", "<", ">"]
COULEURS_EXC = ["tab:blue", "tab:green", "tab:orange", "tab:purple",
                "tab:brown", "tab:cyan", "tab:olive", "tab:gray", "tab:pink"]


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _num(nom):
    """Numéro entier contenu dans un nom (EXCITATION2 -> 2, TEST3 -> 3)."""
    correspondance = re.search(r"(\d+)$", str(nom))
    return int(correspondance.group(1)) if correspondance else 0


def _noms_combi(noms, court=False):
    """'(Accel100, Accel201)' ou, si court, '(100, 201)'."""
    if court:
        noms = [re.sub(r"^[A-Za-z_]+", "", str(n)) or str(n) for n in noms]
    return "(" + ", ".join(map(str, noms)) + ")"


def _dossier(n, test):
    chemin = os.path.join(data_io.chemin_programme(config.DOSSIER_FIGURES),
                          "n_equal_%d" % n, test)
    os.makedirs(chemin, exist_ok=True)
    return chemin


class Traceur:
    """Enregistre / affiche les figures et compte les fichiers produits."""

    def __init__(self, journal=print):
        self.journal = journal
        self.produites = 0
        self.ignorees = 0

    def sauver(self, fig, dossier, nom):
        if config.FIGURES_ENREGISTRER_PNG:
            chemin = os.path.join(dossier, nom + ".png")
            fig.savefig(chemin, dpi=config.FIGURES_DPI, bbox_inches="tight")
            self.journal("    figure : %s" % os.path.relpath(
                chemin, config.DOSSIER_PROGRAMME))
        self.produites += 1
        if not config.FIGURES_INTERACTIF and "--interactif" not in sys.argv:
            plt.close(fig)

    def ignorer(self, nom, raison):
        self.ignorees += 1
        self.journal("    figure NON produite (%s) : %s" % (nom, raison))


def _axe_frequences(ax, frequences):
    """Abscisse en tiers d'octave : échelle log, graduations = bandes."""
    ax.set_xscale("log")
    ax.set_xticks(frequences)
    ax.set_xticklabels(["%g" % f for f in frequences], rotation=45,
                       ha="right")
    ax.minorticks_off()
    ax.set_xlabel("Fréquence en Hz (tiers d'octave)")
    ax.set_ylabel("Niveau en dB")
    ax.grid(True, which="major", alpha=0.3)


def _legende_exterieure(ax):
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8,
              borderaxespad=0.0)


def _couleurs(n):
    carte = plt.get_cmap("viridis")
    if n <= 1:
        return [carte(0.3)]
    return [carte(0.05 + 0.85 * i / (n - 1)) for i in range(n)]


def _acou(test, exc):
    bloc = test["Data_Acou"][exc]
    lac_j = np.array(bloc["Data_3rdOctave_Acou"], dtype=float)
    u = bloc.get("Data_3rdOctave_Acou_Uncertainty")
    u = np.array(u, dtype=float) if (u is not None
                                     and config.FIGURES_INCERTITUDES) else None
    return lac_j, u, float(bloc["Data_GlobalLevel_Acou"])


def _limiter(ordre, valeurs_tri, traceur, nom):
    """Indices à tracer (les meilleurs indices de similarité si trop nombreux)."""
    maxi = config.FIGURES_MAX_COMBINAISONS_TRACEES
    ordre = list(ordre)
    if maxi and len(ordre) > maxi:
        classes = sorted(ordre, key=lambda i: valeurs_tri[i])[:maxi]
        traceur.journal("    %s : %d combinaisons, les %d de plus faible "
                        "similarité sont tracées (FIGURES_MAX_COMBINAISONS_"
                        "TRACEES)." % (nom, len(ordre), maxi))
        return sorted(classes)
    return ordre


def _etiquettes_barres(noms_liste):
    """Étiquettes d'abscisse selon la lisibilité : complètes, courtes ou aucune."""
    k = len(noms_liste)
    if k <= 6:
        return [_noms_combi(n) for n in noms_liste], 0
    if k <= 20:
        return [_noms_combi(n, court=True) for n in noms_liste], 90
    return None, 0


# ---------------------------------------------------------------------------
# Tracés élémentaires
# ---------------------------------------------------------------------------

def _spectre(traceur, dossier, nom_fichier, titre, frequences, lac_j, u_lac,
             courbes):
    """Spectres en tiers d'octave : Lw,ac (rouge, avec incertitudes) + courbes.

    `courbes` : liste de (légende, valeurs).
    """
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    if u_lac is not None:
        ax.errorbar(frequences, lac_j, yerr=u_lac, color=ROUGE, marker="o",
                    capsize=3, lw=2, label="Lw,ac")
    else:
        ax.plot(frequences, lac_j, color=ROUGE, marker="o", lw=2, label="Lw,ac")
    for couleur, (legende, valeurs) in zip(_couleurs(len(courbes)), courbes):
        ax.plot(frequences, valeurs, color=couleur, marker="s", ms=4, lw=1.3,
                label=legende)
    _axe_frequences(ax, frequences)
    ax.set_title(titre, fontsize=10)
    _legende_exterieure(ax)
    traceur.sauver(fig, dossier, nom_fichier)


def _barres(traceur, dossier, nom_fichier, titre, lac, entrees):
    """Niveaux globaux : barre rouge Lw,ac puis une barre par combinaison.

    `entrees` : liste de (légende, noms capteurs, niveau).
    """
    k = len(entrees)
    fig, ax = plt.subplots(figsize=(max(7.0, 0.55 * k + 5.0), 5.5))
    couleurs = _couleurs(k)
    barres = [ax.bar(0, lac, color=ROUGE, label="Lw,ac")]
    for i, (legende, _, niveau) in enumerate(entrees, start=1):
        barres.append(ax.bar(i, niveau, color=couleurs[i - 1], label=legende))
    for b in barres:
        ax.bar_label(b, fmt="%.1f", fontsize=8, padding=2)
    etiquettes, rotation = _etiquettes_barres([e[1] for e in entrees])
    ax.set_xticks(range(k + 1))
    if etiquettes is None:
        ax.set_xticklabels([""] * (k + 1))
        ax.set_xlabel("Combinaisons (voir la légende)")
    else:
        ax.set_xticklabels(["Lw,ac"] + etiquettes, rotation=rotation,
                           ha="center" if rotation == 0 else "right")
        ax.set_xlabel("Capteurs de la combinaison")
    ax.set_ylabel("Niveau global en dB")
    ax.set_ylim(0, max([lac] + [e[2] for e in entrees]) * 1.12)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_title(titre, fontsize=10)
    _legende_exterieure(ax)
    traceur.sauver(fig, dossier, nom_fichier)


# ---------------------------------------------------------------------------
# Figures par test
# ---------------------------------------------------------------------------

def _figures_finales(traceur, n, nom_test, test, frequences, excitations, mono):
    dossier = _dossier(n, nom_test)
    k2 = test["Data_k_2prime"]
    noms = k2["k_2prime_ensemble"]
    for exc in excitations:
        b = k2[exc]
        lac_j, u_lac, lac = _acou(test, exc)
        suffixe = " (unique)" if mono else ""
        ss = b["Spectral_Similarity_m"] if mono else k2["Spectral_Similarity"]
        etiquette_ss = ("Spectral_Similarity_%d : %.4g" % (_num(exc), ss)
                        if mono else "Spectral_Similarity : %.4g" % ss)
        legende = "Lw,vib — %s — (%s)" % (_noms_combi(noms), etiquette_ss)
        _spectre(
            traceur, dossier,
            "combinaison_finale_spectre_n%d_%s_%s" % (n, nom_test, exc),
            "Combinaison finale — %s — %s%s — %s"
            % (_noms_combi(noms), exc, suffixe, nom_test),
            frequences, lac_j, u_lac, [(legende, b["Data_3rdOctave_Vib"])])
        _barres(
            traceur, dossier,
            "combinaison_finale_niveaux_globaux_n%d_%s_%s" % (n, nom_test, exc),
            "Combinaison finale — %s — niveaux globaux — %s%s — %s"
            % (_noms_combi(noms), exc, suffixe, nom_test),
            lac, [(legende, noms, b["Data_GlobalLevel_Vib"])])


def _figures_kprime(traceur, n, nom_test, test, frequences, excitations, mono):
    dossier = _dossier(n, nom_test)
    for exc in excitations:
        lac_j, u_lac, lac = _acou(test, exc)
        if mono:
            bloc = test["Data_k_prime_m"][exc]
            ensemble = bloc["k_prime_m_ensemble"]
            tri = bloc["Spectral_Similarity_m"]
        else:
            bloc = test["Data_k_prime"][exc]
            ensemble = test["Data_k_prime"]["k_prime_ensemble"]
            tri = test["Data_k_prime"]["Spectral_Similarity"]
        if not ensemble:
            traceur.ignorer("k' %s %s" % (exc, nom_test), "ensemble vide")
            continue
        garder = _limiter(range(len(ensemble)), tri, traceur,
                          "k'" + ("_m" if mono else ""))
        ss_m = bloc.get("Spectral_Similarity_m")
        suffixe = " (unique)" if mono else ""

        courbes, entrees = [], []
        for i in garder:
            noms = ensemble[i]
            if mono:
                courbes.append(("Lw,vib — %s" % _noms_combi(noms),
                                bloc["Data_3rdOctave_Vib"][i]))
            else:
                courbes.append(("Lw,vib — %s — (Spectral_Similarity_%d = %.4g)"
                                % (_noms_combi(noms), _num(exc), ss_m[i]),
                                bloc["Data_3rdOctave_Vib"][i]))
            entrees.append(("Lw,vib — %s — (Spectral_Similarity_%d : %.4g)"
                            % (_noms_combi(noms), _num(exc), ss_m[i]),
                            noms, bloc["Data_GlobalLevel_Vib"][i]))
        _spectre(traceur, dossier,
                 "combinaisons_kprime_spectres_n%d_%s_%s" % (n, nom_test, exc),
                 "Combinaisons k’ — %s — %s" % (exc, nom_test),
                 frequences, lac_j, u_lac, courbes)
        _barres(traceur, dossier,
                "combinaisons_kprime_niveaux_globaux_n%d_%s_%s"
                % (n, nom_test, exc),
                ("Combinaisons k’m — niveaux globaux — %s%s — %s"
                 % (exc, suffixe, nom_test)) if mono else
                ("Combinaisons k’ — niveaux globaux — %s — %s" % (exc, nom_test)),
                lac, entrees)


def _figures_similarite(traceur, n, nom_test, test, excitations, mono):
    dossier = _dossier(n, nom_test)
    if mono:
        exc = excitations[0]
        bloc = test["Data_k_prime_m"][exc]
        ensemble = bloc["k_prime_m_ensemble"]
        series = [("Spectral_Similarity_%d" % _num(exc),
                   bloc["Spectral_Similarity_m"], "o", "tab:blue")]
        titre = ("Indice de similarité spectrale des combinaisons k’m — %s "
                 "(unique) — %s" % (exc, nom_test))
        nom = "similarite_spectrale_n%d_%s_%s" % (n, nom_test, exc)
    else:
        dkp = test["Data_k_prime"]
        ensemble = dkp["k_prime_ensemble"]
        series = [("Spectral_Similarity_%d (%s)" % (_num(e), e),
                   dkp[e]["Spectral_Similarity_m"],
                   MARQUEURS[i % len(MARQUEURS)],
                   COULEURS_EXC[i % len(COULEURS_EXC)])
                  for i, e in enumerate(excitations)]
        series.append(("Toutes les excitations", dkp["Spectral_Similarity"],
                       "*", "black"))
        titre = "Indices de similarité spectrale des combinaisons k’ — %s" % nom_test
        nom = "similarite_spectrale_n%d_%s_toutes_excitations" % (n, nom_test)
    if not ensemble:
        traceur.ignorer("similarité %s" % nom_test, "ensemble vide")
        return
    k = len(ensemble)
    fig, ax = plt.subplots(figsize=(max(8.0, 0.4 * k + 5.0), 5.5))
    x = np.arange(k)
    for legende, valeurs, marqueur, couleur in series:
        ax.scatter(x, valeurs, marker=marqueur, color=couleur, s=55,
                   label=legende, zorder=3)
    etiquettes, rotation = _etiquettes_barres(ensemble)
    if k > 60:
        etiquettes = None
    ax.set_xticks(x)
    if etiquettes is None:
        ax.set_xticklabels([""] * k)
        ax.set_xlabel("Combinaisons (%d, trop nombreuses pour être nommées)" % k)
    else:
        ax.set_xticklabels(etiquettes, rotation=90 if k > 6 else 0,
                           ha="right" if k > 6 else "center", fontsize=8)
        ax.set_xlabel("Capteurs de la combinaison")
    ax.set_ylabel("Indice de similarité spectrale (sans unité)")
    ax.grid(True, alpha=0.3)
    ax.set_title(titre, fontsize=10)
    _legende_exterieure(ax)
    traceur.sauver(fig, dossier, nom)


def _figures_rayonnement(traceur, n, nom_test, test, frequences, excitations,
                         mono):
    dossier = _dossier(n, nom_test)
    k2 = test["Data_k_2prime"]
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    manque_u = False

    def courbe(valeurs, u, legende, couleur, marqueur, **style):
        nonlocal manque_u
        valeurs = np.array(valeurs, dtype=float)
        if config.FIGURES_INCERTITUDES and u is not None:
            ax.errorbar(frequences, valeurs, yerr=np.array(u, dtype=float),
                        color=couleur, marker=marqueur, capsize=3,
                        label=legende, **style)
        else:
            manque_u = manque_u or config.FIGURES_INCERTITUDES
            ax.plot(frequences, valeurs, color=couleur, marker=marqueur,
                    label=legende, **style)

    for i, exc in enumerate(excitations):
        b = k2[exc]
        courbe(b["Data_3rdOctave_Radiation_Factor"],
               b.get("Data_3rdOctave_Radiation_Factor_Uncertainty"), exc,
               COULEURS_EXC[i % len(COULEURS_EXC)], MARQUEURS[i % len(MARQUEURS)],
               lw=1.3)
    if not mono:
        courbe(k2["Data_3rdOctave_Radiation_Factor_Moyen"],
               k2.get("Data_3rdOctave_Radiation_Factor_Moyen_Uncertainty"),
               "Moyenne des excitations", "black", "*", lw=2.2)
    if manque_u:
        traceur.journal("    incertitudes du facteur de rayonnement absentes "
                        "du fichier (INCERTITUDES_DANS_RESULTATS = False) : "
                        "barres non tracées.")
    ax.set_yscale("log")
    _axe_frequences(ax, frequences)
    ax.set_ylabel("Facteur de rayonnement (sans unité, échelle log)")
    noms = _noms_combi(k2["k_2prime_ensemble"])
    if mono:
        titre = "Facteurs de rayonnement — %s (unique)— %s" % (excitations[0],
                                                               nom_test)
        nom = "facteur_rayonnement_n%d_%s_%s" % (n, nom_test, excitations[0])
    else:
        titre = "Facteurs de rayonnement — %s" % nom_test
        nom = "facteur_rayonnement_n%d_%s_toutes_excitations" % (n, nom_test)
    ax.set_title("%s\ncombinaison k_2prime : %s" % (titre, noms), fontsize=10)
    _legende_exterieure(ax)
    traceur.sauver(fig, dossier, nom)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def tracer(resultats, journal=print):
    """Trace toutes les figures activées à partir du dictionnaire de résultats."""
    racines = [c for c in resultats if str(c).startswith("DataCristofori")]
    if len(racines) != 1:
        raise data_io.ErreurDonnees(
            "Une clé racine DataCristofori* est attendue, %d trouvée(s)."
            % len(racines))
    racine = resultats[racines[0]]
    journal("")
    journal("=" * 64)
    journal("Figures")
    journal("=" * 64)
    groupes = {
        "combinaison finale": config.FIGURES_GROUPE_COMBINAISON_FINALE,
        "k'/k'_m": config.FIGURES_GROUPE_K_PRIME,
        "similarité": config.FIGURES_GROUPE_SIMILARITE,
        "rayonnement": config.FIGURES_GROUPE_RAYONNEMENT,
    }
    actifs = [g for g, a in groupes.items() if a]
    journal("Groupes actifs : %s" % (", ".join(actifs) or "aucun"))
    if not config.FIGURES_ENREGISTRER_PNG and not config.FIGURES_INTERACTIF:
        journal("FIGURES_ENREGISTRER_PNG et FIGURES_INTERACTIF sont faux : "
                "aucune figure produite.")
        return 0
    traceur = Traceur(journal)
    for cle_n in sorted(racine, key=_num):
        n = _num(cle_n)
        for nom_test in sorted(racine[cle_n], key=_num):
            test = racine[cle_n][nom_test]
            excitations = sorted((c for c in test["Data_Acou"]
                                  if c.startswith("EXCITATION")), key=_num)
            mono = len(excitations) == 1
            frequences = np.array(test["Data_Acou"]["frq_3rdOctave"], dtype=float)
            journal("  n = %d, %s (%d excitation(s))"
                    % (n, nom_test, len(excitations)))
            if groupes["combinaison finale"]:
                _figures_finales(traceur, n, nom_test, test, frequences,
                                 excitations, mono)
            if groupes["k'/k'_m"]:
                _figures_kprime(traceur, n, nom_test, test, frequences,
                                excitations, mono)
            if groupes["similarité"]:
                _figures_similarite(traceur, n, nom_test, test, excitations,
                                    mono)
            if groupes["rayonnement"]:
                _figures_rayonnement(traceur, n, nom_test, test, frequences,
                                     excitations, mono)
    journal("Figures produites : %d ; non produites : %d"
            % (traceur.produites, traceur.ignorees))
    if config.FIGURES_INTERACTIF or "--interactif" in sys.argv:
        plt.show()
    return traceur.produites


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    chemin = config.FICHIER_SORTIE
    if "--fichier" in arguments:
        indice = arguments.index("--fichier")
        if indice + 1 >= len(arguments):
            print("ERREUR : --fichier attend un chemin.", file=sys.stderr)
            return 1
        chemin = arguments[indice + 1]
    try:
        tracer(data_io.lire_resultats(chemin))
    except data_io.ErreurDonnees as err:
        print("ERREUR : %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
