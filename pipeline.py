# -*- coding: utf-8 -*-
"""Enchaînement commun aux deux méthodes (phase 1 + phase 2 + écriture).

Ce module est le seul ajout aux sept fichiers prévus par le cahier des
charges. Il est justifié par l'exigence de mutualisation : sans lui, la
totalité de la chaîne (lecture, validation, diagnostic de faisabilité,
exécution des tests, assemblage des blocs de résultats, écriture, affichage)
serait dupliquée à l'identique entre main1.py et main2.py.

main1.py et main2.py se réduisent ainsi à la déclaration de ce qui distingue
réellement les deux méthodes :

* le nombre de capteurs de la combinaison initiale (5 ou 10) ;
* la présence du facteur de rayonnement dans les calculs (ISO 7849-2).
"""

from __future__ import annotations

import sys

import calculs
import config
import data_io
import selection_capteurs as selection


LARGEUR = 60


def _titre(texte, journal):
    journal("=" * LARGEUR)
    journal(texte)
    journal("=" * LARGEUR)


def _formater_liste(valeurs, decimales=3, maximum=12):
    """Formate une liste de nombres de façon compacte pour la console."""
    extrait = valeurs[:maximum]
    texte = ", ".join(("%." + str(decimales) + "g") % valeur
                      for valeur in extrait)
    if len(valeurs) > maximum:
        texte += ", ..."
    return "[" + texte + "]"


def preparer_donnees(n_init, journal=print):
    """Lit, valide et met en forme les données nécessaires aux deux méthodes.

    Renvoie un dictionnaire de contexte contenant les données de mesure, la
    liste des excitations, les capteurs disponibles, les coordonnées et les
    niveaux vibratoires par excitation.
    """
    donnees = data_io.lire_mesures()
    resume = data_io.valider_mesures(donnees, n_capteurs_min=n_init)

    excitations = resume["excitations"]
    noms_capteurs = resume["capteurs"]
    frequences = resume["frequences"]

    indices_disponibles = data_io.indices_capteurs_disponibles(noms_capteurs)
    if len(indices_disponibles) < n_init:
        raise data_io.ErreurDonnees(
            "Après exclusion de %d capteur(s), il reste %d capteurs "
            "utilisables ; la combinaison initiale en demande %d."
            % (len(config.CAPTEURS_EXCLUS), len(indices_disponibles), n_init)
        )

    # Les coordonnées servent uniquement à favoriser la dispersion spatiale du
    # tirage. Elles sont identiques d'une excitation à l'autre dans les jeux de
    # mesures ; celles de la première excitation font référence.
    _, coordonnees, _ = data_io.donnees_accel(donnees, excitations[0])

    niveaux_par_excitation = {}
    for excitation in excitations:
        _, _, niveaux = data_io.donnees_accel(donnees, excitation)
        niveaux_par_excitation[excitation] = niveaux

    journal("Fichier source          : %s" % config.FICHIER_ENTREE)
    journal("Excitations détectées   : %d (%s)"
            % (len(excitations), ", ".join(excitations)))
    journal("Capteurs dans le fichier: %d" % len(noms_capteurs))
    if config.CAPTEURS_EXCLUS:
        journal("Capteurs exclus         : %d (%s)"
                % (len(config.CAPTEURS_EXCLUS),
                   ", ".join(config.CAPTEURS_EXCLUS)))
    journal("Capteurs utilisables    : %d" % len(indices_disponibles))
    journal("Tiers d'octave          : %d (%.0f Hz a %.0f Hz)"
            % (len(frequences), frequences[0], frequences[-1]))
    journal("Nombre de tests (config): %d" % config.Nb_Test)
    journal("Capteurs initiaux       : %d" % n_init)
    journal("Surface rayonnante S    : %g m2 (S0 = %g m2)"
            % (config.S, config.S0))

    return {
        "donnees": donnees,
        "resume": resume,
        "excitations": excitations,
        "noms_capteurs": noms_capteurs,
        "frequences": frequences,
        "indices_disponibles": indices_disponibles,
        "coordonnees": coordonnees,
        "niveaux_par_excitation": niveaux_par_excitation,
    }


def controler_faisabilite(contexte, n_init, facteur, journal=print):
    """Affiche le diagnostic de faisabilité et signale les cas impossibles.

    Renvoie le diagnostic. Quand le critère max/min est hors d'atteinte, aucun
    tirage ne peut aboutir : il est inutile de lancer les tests, le programme
    doit s'arrêter avec un message explicite.
    """
    diagnostic = selection.diagnostic_faisabilite(
        contexte["niveaux_par_excitation"], contexte["indices_disponibles"],
        facteur=facteur,
    )
    borne = selection.borne_indicative_nb_tests(
        len(contexte["indices_disponibles"]), n_init
    )

    journal("")
    journal("--- Diagnostic préalable ---")
    if config.SEUIL_ECART_DB is None:
        journal("Critère : ecart_j < %g x n (règle normative de la "
                "norme appliquée)" % facteur)
    else:
        journal("Critère : ecart_j < %.1f dB (SEUIL_ECART_DB, dérogation "
                "explicite)" % config.SEUIL_ECART_DB)
    journal("Ecart max/min maximal avec les %d capteurs utilisables : %.1f dB"
            % (diagnostic["n_capteurs_disponibles"],
               diagnostic["ecart_maximal"]))
    journal("Combinaisons distinctes possibles (ordre de grandeur) : %d"
            % borne["borne_paquet"])
    if config.Nb_Test > borne["borne_paquet"]:
        journal("ATTENTION : Nb_Test = %d dépasse cet ordre de grandeur ; "
                "des redémarrages de tests sont probables."
                % config.Nb_Test)

    if selection.mode_seuil_fixe():
        # En seuil fixe, l'ajout de capteurs ne peut qu'aggraver l'écart : la
        # faisabilité se joue entièrement sur le tirage initial, dont le taux
        # d'acceptation est estimé par échantillonnage.
        estimation = selection.taux_acceptation_initiale(
            contexte["niveaux_par_excitation"], contexte["coordonnees"],
            contexte["indices_disponibles"], n_init,
            selection.creer_generateur(graine=0)[0], facteur=facteur,
        )
        journal("Tirages initiaux de %d capteurs satisfaisant le seuil : "
                "%.0f %% (sur %d tirages simulés, meilleur écart %.1f dB)"
                % (n_init, 100.0 * estimation["taux"], estimation["essais"],
                   estimation["meilleur_ecart"]))
        if estimation["taux"] == 0.0:
            journal("")
            journal("ARRET : aucun tirage de %d capteurs ne respecte le seuil "
                    "de %.1f dB (meilleur écart obtenu : %.1f dB)."
                    % (n_init, diagnostic["seuil"],
                       estimation["meilleur_ecart"]))
            journal("Relever SEUIL_ECART_DB au-dessus de cette valeur, ou "
                    "revoir les capteurs retenus.")
            diagnostic = dict(diagnostic)
            diagnostic["faisable"] = False

    if not diagnostic["faisable"] and diagnostic["bandes_bloquantes"]:
        exemple = diagnostic["bandes_bloquantes"][0]
        journal("")
        journal("ARRET : le critère max/min ne peut être satisfait par AUCUNE "
                "combinaison.")
        journal("Avec la totalité des %d capteurs utilisables, l'écart reste "
                "supérieur ou égal au seuil sur %d bande(s), par exemple %s "
                "bande %d : ecart = %.1f dB pour un seuil de %.1f."
                % (diagnostic["n_capteurs_disponibles"],
                   len(diagnostic["bandes_bloquantes"]), exemple[0],
                   exemple[1] + 1, exemple[2], diagnostic["seuil"]))
        journal("L'écart max/min ne fait que croître quand des capteurs sont "
                "ajoutés, alors que le seuil ne gagne que %g par capteur : "
                "changer de tirage n'y change rien." % facteur)
        journal("Solutions possibles :")
        journal("  - vérifier les capteurs aberrants et les inscrire dans "
                "CAPTEURS_EXCLUS ;")
        journal("  - vérifier l'unité et le référencement des niveaux "
                "Data_3rdOctave_Vel ;")
        journal("  - renseigner SEUIL_ECART_DB dans config.py pour appliquer "
                "un seuil en dB décidé et tracé.")
    return diagnostic


def executer_methode(nom_methode, n_init, cle_racine, chemin_sortie,
                     avec_facteur_rayonnement, facteur_critere=1.0,
                     journal=print):
    """Exécute une méthode complète et écrit son fichier de résultats.

    Renvoie (chemin du fichier écrit, dictionnaire des tests, métadonnées).
    """
    _titre(nom_methode, journal)

    contexte = preparer_donnees(n_init, journal=journal)
    diagnostic = controler_faisabilite(contexte, n_init, facteur_critere,
                                       journal=journal)
    if not diagnostic["faisable"]:
        raise selection.SelectionImpossible(
            "Critère max/min inatteignable avec les données fournies "
            "(voir le diagnostic ci-dessus)."
        )

    generateur, graine = selection.creer_generateur()
    journal("Graine aléatoire utilisée : %d%s"
            % (graine, "" if config.RANDOM_SEED is not None
               else " (tirée au hasard, recopiable dans RANDOM_SEED)"))

    # --- Facteur de rayonnement : calculé une seule fois, avant les tests ---
    facteur_rayonnement = None
    detail_facteur = None
    if avec_facteur_rayonnement:
        facteur_rayonnement, detail_facteur = calculs.calculer_facteur_rayonnement(
            contexte["donnees"], contexte["excitations"],
            data_io.donnees_accel, data_io.donnees_micro,
            contexte["indices_disponibles"],
        )
        journal("")
        journal("--- Facteur de rayonnement (tous les capteurs utilisables) ---")
        for nom_excitation, facteurs in detail_facteur.items():
            journal("  %s : %s" % (nom_excitation, _formater_liste(facteurs)))
        if len(detail_facteur) > 1:
            journal("  Moyenne arithmétique : %s"
                    % _formater_liste(facteur_rayonnement))

    # --- Phase 1 : combinaisons finales ---
    journal("")
    journal("--- Phase 1 : sélection des capteurs ---")
    tests_selection = selection.generer_combinaisons_finales(
        contexte["excitations"], contexte["niveaux_par_excitation"],
        contexte["coordonnees"], contexte["indices_disponibles"], n_init,
        config.Nb_Test, generateur, journal=journal,
        noms_capteurs=contexte["noms_capteurs"], facteur=facteur_critere,
    )

    # --- Phase 2 : calculs avec la combinaison finale figée ---
    journal("")
    journal("--- Phase 2 : calculs ---")
    tests = {}
    resume_tests = []
    for description in tests_selection:
        nom_test = description["test"]
        combinaison = description["combinaison"]
        bloc_test = {}
        for excitation in contexte["excitations"]:
            noms, coordonnees, niveaux_vel = data_io.donnees_accel(
                contexte["donnees"], excitation
            )
            frequences, spectre_acou, global_acou = data_io.donnees_micro(
                contexte["donnees"], excitation
            )
            bloc_test[excitation] = calculs.bloc_excitation(
                frequences, spectre_acou, global_acou, noms, coordonnees,
                niveaux_vel, combinaison,
                facteur_rayonnement=facteur_rayonnement,
            )
        tests[nom_test] = bloc_test
        if avec_facteur_rayonnement:
            journal("  %s : facteur de rayonnement = %s"
                    % (nom_test, _formater_liste(facteur_rayonnement)))
        premiere = contexte["excitations"][0]
        journal("  %s : %d capteurs, Lw,vib global (%s) = %.1f dB, "
                "Lw,ac global = %.1f dB"
                % (nom_test, len(combinaison), premiere,
                   bloc_test[premiere]["Data_GlobalLevel_Vib"],
                   bloc_test[premiere]["Data_GlobalLevel_Acou"]))
        resume_tests.append({
            "test": nom_test,
            "nb_capteurs": len(combinaison),
            "capteurs": [contexte["noms_capteurs"][indice]
                         for indice in combinaison],
            "capteurs_initiaux": [contexte["noms_capteurs"][indice]
                                  for indice in description["initiale"]],
            "capteurs_ajoutes_par_excitation": {
                excitation: [contexte["noms_capteurs"][indice]
                             for indice in ajouts]
                for excitation, ajouts in description["ajouts"].items()
            },
            "tentatives": description["tentatives"],
        })

    # --- Écriture ---
    extra = {
        "nb_capteurs_utilisables": len(contexte["indices_disponibles"]),
        "n_capteurs_initiaux": n_init,
        "facteur_critere": facteur_critere,
        "ecart_maximal_tous_capteurs_dB": diagnostic["ecart_maximal"],
        "tests": resume_tests,
    }
    if avec_facteur_rayonnement:
        extra["facteur_rayonnement"] = {
            "valeur_utilisee": list(facteur_rayonnement),
            "excitations_utilisees": list(config.Excitations_RF),
            "detail_par_excitation": {nom: list(valeurs)
                                      for nom, valeurs
                                      in detail_facteur.items()},
            "base_capteurs": "tous les capteurs utilisables",
        }
    metadonnees = data_io.construire_metadonnees(
        nom_methode, contexte["resume"], graine, extra=extra
    )
    chemin = data_io.ecrire_resultats(
        chemin_sortie, cle_racine, tests, metadonnees
    )

    journal("")
    journal("Fichier de résultats écrit : %s" % chemin)
    journal("Tracé des figures : python figures.py --fichier %s"
            % chemin_sortie)
    return chemin, tests, metadonnees


def executer_en_ligne_de_commande(nom_methode, n_init, cle_racine,
                                  chemin_sortie, avec_facteur_rayonnement,
                                  facteur_critere=1.0):
    """Point d'entrée des programmes principaux, avec gestion des erreurs.

    Renvoie le code de sortie du processus : 0 succès, 1 données invalides,
    2 sélection impossible.
    """
    try:
        executer_methode(nom_methode, n_init, cle_racine, chemin_sortie,
                         avec_facteur_rayonnement,
                         facteur_critere=facteur_critere)
    except data_io.ErreurDonnees as err:
        print("")
        print("ERREUR de données : %s" % err, file=sys.stderr)
        return 1
    except selection.SelectionImpossible as err:
        print("")
        print("ERREUR de sélection : %s" % err, file=sys.stderr)
        return 2
    except ValueError as err:
        print("")
        print("ERREUR de calcul : %s" % err, file=sys.stderr)
        return 1
    return 0
