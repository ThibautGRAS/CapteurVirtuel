# -*- coding: utf-8 -*-
"""Tracé des figures à partir des fichiers de résultats.

Script autonome : il relit DataISO7849_1.json et/ou DataISO7849_2.json déjà
produits par main1.py et main2.py, et n'effectue aucun calcul normatif.

Pour chaque fichier de résultats et chaque excitation, deux figures sont
produites :

* un graphique des spectres en tiers d'octave : le niveau de puissance
  acoustique en rouge (Lw, ac) et le niveau de puissance vibratoire de chaque
  test (Lw,vib, testx) ;
* un diagramme en barres des niveaux globaux correspondants, avec les mêmes
  couleurs et les mêmes légendes, et la valeur en dB inscrite sur chaque barre.

Usage :
    python figures.py                        # les deux fichiers, PNG
    python figures.py --interactif           # PNG + fenêtres matplotlib
    python figures.py --fichier DataISO7849_2.json
    python figures.py --dossier resultats --dpi 200 --pas-de-png --interactif
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib

import config
import data_io


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _numero_methode(cle_racine):
    """Renvoie '1' ou '2' à partir de la clé racine DataISO7849_x."""
    return str(cle_racine).replace("DataISO7849_", "")


def _numero_test(nom_test):
    """Renvoie le numéro d'un test sous forme de texte ('TEST3' -> '3')."""
    return str(nom_test).replace("TEST", "")


def _couleurs_tests(nb_tests, pyplot):
    """Palette de couleurs distinctes pour les courbes de puissance vibratoire.

    Le rouge étant réservé à la courbe acoustique, la palette choisie dans
    config.FIGURES_PALETTE_VIB l'évite.
    """
    carte = pyplot.get_cmap(config.FIGURES_PALETTE_VIB)
    if nb_tests == 1:
        return [carte(0.35)]
    return [carte(indice / float(nb_tests - 1) * 0.9) for indice in
            range(nb_tests)]


def _nom_fichier(dossier, cle_racine, excitation, suffixe):
    return os.path.join(
        dossier, "ISO7849-%s_%s_%s.png"
        % (_numero_methode(cle_racine), excitation, suffixe)
    )


# ---------------------------------------------------------------------------
# Tracés
# ---------------------------------------------------------------------------

def tracer_spectres(pyplot, cle_racine, excitation, frequences, spectre_acou,
                    spectres_vib, couleurs):
    """Graphique des spectres en tiers d'octave pour une excitation.

    `spectres_vib` est une liste de couples (nom du test, spectre).
    """
    figure, axes = pyplot.subplots(figsize=(9.0, 5.5))

    for (nom_test, spectre), couleur in zip(spectres_vib, couleurs):
        axes.plot(frequences, spectre, marker="o", markersize=4,
                  linewidth=1.4, color=couleur,
                  label="Lw,vib, test%s" % _numero_test(nom_test))
    axes.plot(frequences, spectre_acou, marker="s", markersize=5, linewidth=2.2,
              color=config.FIGURES_COULEUR_ACOU, label="Lw, ac", zorder=5)

    axes.set_xscale("log")
    axes.set_xticks(frequences)
    axes.set_xticklabels(["%g" % frequence for frequence in frequences])
    axes.minorticks_off()
    axes.set_xlabel("Tiers d'octave (Hz)")
    axes.set_ylabel("Niveau (dB)")
    axes.set_title("ISO7849-%s , %s" % (_numero_methode(cle_racine),
                                        excitation))
    axes.grid(True, which="major", linestyle=":", linewidth=0.7, alpha=0.7)
    axes.legend(loc="best", fontsize=9)
    figure.tight_layout()
    return figure


def tracer_globaux(pyplot, cle_racine, excitation, global_acou, globaux_vib,
                   couleurs):
    """Diagramme en barres des niveaux globaux pour une excitation.

    `globaux_vib` est une liste de couples (nom du test, niveau global).
    """
    figure, axes = pyplot.subplots(figsize=(11.0, 5.5))

    etiquettes = ["Lw, ac"] + ["Lw,vib, test%s" % _numero_test(nom)
                               for nom, _ in globaux_vib]
    valeurs = [global_acou] + [valeur for _, valeur in globaux_vib]
    couleurs_barres = [config.FIGURES_COULEUR_ACOU] + list(couleurs)

    positions = range(len(valeurs))
    barres = axes.bar(positions, valeurs, color=couleurs_barres, width=0.65)
    for barre, valeur in zip(barres, valeurs):
        axes.annotate("%.1f dB" % valeur,
                      xy=(barre.get_x() + barre.get_width() / 2.0, valeur),
                      xytext=(0, 4), textcoords="offset points",
                      ha="center", va="bottom", fontsize=9)

    axes.set_xticks(list(positions))
    axes.set_xticklabels(etiquettes, rotation=30, ha="right", fontsize=9)
    axes.set_ylabel("Niveau global (dB)")
    axes.set_title("ISO7849-%s, %s, niveaux globaux"
                   % (_numero_methode(cle_racine), excitation))
    axes.grid(True, axis="y", linestyle=":", linewidth=0.7, alpha=0.7)
    marge = max(3.0, 0.05 * (max(valeurs) - min(min(valeurs), 0.0)))
    axes.set_ylim(min(0.0, min(valeurs) - marge), max(valeurs) + 2.5 * marge)

    # Légende reprenant les mêmes couleurs et les mêmes intitulés que le
    # graphique des spectres, pour que les deux figures se lisent ensemble.
    # Elle est placée hors de la zone de tracé : à l'intérieur, elle
    # recouvrirait la valeur inscrite au-dessus des premières barres.
    axes.legend(barres, etiquettes, loc="upper left",
                bbox_to_anchor=(1.01, 1.0), fontsize=9, borderaxespad=0.0)
    figure.tight_layout()
    return figure


def tracer_fichier(chemin, pyplot, dossier_figures=None, enregistrer=True,
                   dpi=None, journal=print):
    """Trace toutes les figures d'un fichier de résultats.

    Renvoie la liste des chemins PNG écrits.
    """
    cle_racine, tests, metadonnees = data_io.lire_resultats(chemin)
    noms_tests = data_io.trier_tests(tests)
    if not noms_tests:
        raise data_io.ErreurDonnees(
            "%s ne contient aucun TESTx à tracer." % chemin
        )

    dossier = dossier_figures or config.DOSSIER_FIGURES
    dpi = dpi or config.FIGURES_DPI
    if enregistrer and not os.path.isdir(dossier):
        os.makedirs(dossier, exist_ok=True)

    excitations = data_io.lister_excitations(tests[noms_tests[0]])
    couleurs = _couleurs_tests(len(noms_tests), pyplot)

    journal("%s : %s, %d test(s), %d excitation(s)"
            % (os.path.basename(chemin), cle_racine, len(noms_tests),
               len(excitations)))
    if metadonnees.get("date_execution"):
        journal("  calculé le %s, graine %s"
                % (metadonnees["date_execution"],
                   metadonnees.get("graine_aleatoire", "?")))

    fichiers = []
    for excitation in excitations:
        reference = tests[noms_tests[0]][excitation]
        frequences = reference["frq_3rdOctave"]
        spectre_acou = reference["Data_3rdOctave_Acou"]
        global_acou = reference["Data_GlobalLevel_Acou"]

        spectres_vib = [(nom, tests[nom][excitation]["Data_3rdOctave_Vib"])
                        for nom in noms_tests]
        globaux_vib = [(nom, tests[nom][excitation]["Data_GlobalLevel_Vib"])
                       for nom in noms_tests]

        figure_spectres = tracer_spectres(
            pyplot, cle_racine, excitation, frequences, spectre_acou,
            spectres_vib, couleurs
        )
        figure_globaux = tracer_globaux(
            pyplot, cle_racine, excitation, global_acou, globaux_vib, couleurs
        )

        if enregistrer:
            chemin_spectres = _nom_fichier(dossier, cle_racine, excitation,
                                           "spectres")
            chemin_globaux = _nom_fichier(dossier, cle_racine, excitation,
                                          "globaux")
            figure_spectres.savefig(chemin_spectres, dpi=dpi)
            figure_globaux.savefig(chemin_globaux, dpi=dpi)
            fichiers.extend([chemin_spectres, chemin_globaux])
            journal("  %s" % chemin_spectres)
            journal("  %s" % chemin_globaux)

    return fichiers


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------

def analyser_arguments(arguments=None):
    analyseur = argparse.ArgumentParser(
        description="Trace les figures des résultats ISO 7849-1 et 7849-2."
    )
    analyseur.add_argument(
        "--fichier", action="append", dest="fichiers", metavar="CHEMIN",
        help="fichier de résultats à tracer (option répétable). Par défaut : "
             "les fichiers déclarés dans config.py s'ils existent.",
    )
    analyseur.add_argument(
        "--dossier", dest="dossier", default=None, metavar="DOSSIER",
        help="dossier d'enregistrement des PNG (défaut : config.DOSSIER_FIGURES)",
    )
    analyseur.add_argument(
        "--dpi", type=int, default=None,
        help="résolution des PNG (défaut : config.FIGURES_DPI)",
    )
    analyseur.add_argument(
        "--interactif", action="store_true",
        help="affiche les figures dans des fenêtres matplotlib",
    )
    analyseur.add_argument(
        "--pas-de-png", action="store_true", dest="pas_de_png",
        help="n'enregistre aucun fichier PNG",
    )
    return analyseur.parse_args(arguments)


def main(arguments=None):
    options = analyser_arguments(arguments)

    interactif = options.interactif or config.FIGURES_INTERACTIF
    if not interactif:
        matplotlib.use("Agg")
    import matplotlib.pyplot as pyplot  # après le choix du moteur de rendu

    fichiers = options.fichiers
    if not fichiers:
        fichiers = [chemin for chemin in (config.FICHIER_SORTIE_ISO1,
                                          config.FICHIER_SORTIE_ISO2)
                    if os.path.isfile(chemin)]
    if not fichiers:
        print("Aucun fichier de résultats trouvé (%s, %s). Lancer d'abord "
              "main1.py et/ou main2.py."
              % (config.FICHIER_SORTIE_ISO1, config.FICHIER_SORTIE_ISO2),
              file=sys.stderr)
        return 1

    enregistrer = config.FIGURES_ENREGISTRER_PNG and not options.pas_de_png
    total = 0
    for chemin in fichiers:
        try:
            ecrits = tracer_fichier(
                chemin, pyplot, dossier_figures=options.dossier,
                enregistrer=enregistrer, dpi=options.dpi,
            )
        except data_io.ErreurDonnees as err:
            print("ERREUR : %s" % err, file=sys.stderr)
            return 1
        total += len(ecrits)

    if enregistrer:
        print("%d figure(s) PNG enregistrée(s)." % total)
    if interactif:
        print("Fermer les fenêtres pour terminer.")
        pyplot.show()
    else:
        pyplot.close("all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
