# -*- coding: utf-8 -*-
"""Lecture, validation et écriture des fichiers JSON.

Ce module est le seul point de contact avec le disque pour les données de
mesure. Il ne contient aucune règle de calcul ni de sélection.

Le fichier d'entrée n'est ouvert qu'en lecture : il n'est jamais réécrit.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime

import config


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ErreurDonnees(Exception):
    """Structure ou contenu du fichier de mesures invalide."""


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

_MOTIF_EXCITATION = re.compile(r"^EXCITATION(\d+)$")


def lire_mesures(chemin=None):
    """Lit le fichier de mesures et renvoie le dictionnaire brut.

    Le fichier est ouvert en lecture seule. Aucune donnée n'y est écrite.
    """
    chemin = chemin or config.FICHIER_ENTREE
    if not os.path.isfile(chemin):
        raise ErreurDonnees(
            "Fichier de mesures introuvable : %s\n"
            "Vérifier config.FICHIER_ENTREE et le dossier de travail." % chemin
        )
    try:
        with open(chemin, "r", encoding="utf-8") as flux:
            donnees = json.load(flux)
    except json.JSONDecodeError as err:
        raise ErreurDonnees(
            "Le fichier %s n'est pas un JSON valide : %s" % (chemin, err)
        ) from err
    if not isinstance(donnees, dict):
        raise ErreurDonnees(
            "Le fichier %s doit contenir un objet JSON à la racine." % chemin
        )
    return donnees


def lister_excitations(donnees):
    """Renvoie les clés EXCITATIONx triées par numéro croissant.

    Le tri est NUMÉRIQUE : EXCITATION2 vient avant EXCITATION10.
    Le bloc BDF et toute autre clé sont ignorés.
    """
    trouvees = []
    for cle in donnees:
        correspondance = _MOTIF_EXCITATION.match(str(cle))
        if correspondance:
            trouvees.append((int(correspondance.group(1)), cle))
    trouvees.sort(key=lambda couple: couple[0])
    return [cle for _, cle in trouvees]


def numero_excitation(nom_excitation):
    """Renvoie le numéro entier d'une clé EXCITATIONx."""
    correspondance = _MOTIF_EXCITATION.match(str(nom_excitation))
    if not correspondance:
        raise ErreurDonnees("Nom d'excitation inattendu : %r" % (nom_excitation,))
    return int(correspondance.group(1))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _est_nombre_fini(valeur):
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool) \
        and math.isfinite(float(valeur))


def _valider_vecteur(valeur, nom, longueur_attendue=None):
    if not isinstance(valeur, list):
        raise ErreurDonnees("%s doit être une liste." % nom)
    if longueur_attendue is not None and len(valeur) != longueur_attendue:
        raise ErreurDonnees(
            "%s contient %d valeurs, %d attendues."
            % (nom, len(valeur), longueur_attendue)
        )
    for indice, element in enumerate(valeur):
        if not _est_nombre_fini(element):
            raise ErreurDonnees(
                "%s[%d] = %r n'est pas un nombre fini (NaN, infini ou texte)."
                % (nom, indice, element)
            )
    return valeur


def valider_mesures(donnees, n_capteurs_min=1):
    """Vérifie la structure et la cohérence du fichier de mesures.

    Contrôle, pour chaque excitation : présence des blocs Accel et Micro,
    présence et cohérence des champs utilisés, validité numérique des données,
    et nombre de capteurs suffisant. Lève ErreurDonnees avec un message
    explicite au premier défaut rencontré.

    Renvoie un dictionnaire de synthèse : excitations, capteurs, fréquences.
    """
    excitations = lister_excitations(donnees)
    if not excitations:
        raise ErreurDonnees(
            "Aucune clé EXCITATIONx trouvée dans le fichier de mesures. "
            "Clés présentes : %s" % ", ".join(sorted(map(str, donnees)))
        )

    noms_reference = None
    frequences_reference = None

    for excitation in excitations:
        bloc = donnees[excitation]
        if not isinstance(bloc, dict):
            raise ErreurDonnees("%s doit être un objet JSON." % excitation)
        for sous_bloc in ("Accel", "Micro"):
            if sous_bloc not in bloc or not isinstance(bloc[sous_bloc], dict):
                raise ErreurDonnees(
                    "%s : bloc %s absent ou invalide." % (excitation, sous_bloc)
                )

        accel = bloc["Accel"]
        micro = bloc["Micro"]

        for champ in ("frq_3rdOctave", "sensor_name", "sensor_coordinates",
                      "Data_3rdOctave_Vel"):
            if champ not in accel:
                raise ErreurDonnees(
                    "%s.Accel : champ %s absent." % (excitation, champ)
                )
        for champ in ("frq_3rdOctave", "Data_3rdOctave_Lw",
                      "Data_GlobalLevel_Lw"):
            if champ not in micro:
                raise ErreurDonnees(
                    "%s.Micro : champ %s absent." % (excitation, champ)
                )

        frequences = _valider_vecteur(
            accel["frq_3rdOctave"], "%s.Accel.frq_3rdOctave" % excitation
        )
        if not frequences:
            raise ErreurDonnees(
                "%s.Accel.frq_3rdOctave est vide." % excitation
            )
        n_frequences = len(frequences)

        noms = accel["sensor_name"]
        if not isinstance(noms, list) or not noms:
            raise ErreurDonnees(
                "%s.Accel.sensor_name doit être une liste non vide." % excitation
            )
        if len(set(map(str, noms))) != len(noms):
            raise ErreurDonnees(
                "%s.Accel.sensor_name contient des doublons." % excitation
            )
        n_capteurs = len(noms)

        coordonnees = accel["sensor_coordinates"]
        if not isinstance(coordonnees, list) or len(coordonnees) != n_capteurs:
            raise ErreurDonnees(
                "%s.Accel.sensor_coordinates : %d entrées pour %d capteurs."
                % (excitation, len(coordonnees) if isinstance(coordonnees, list)
                   else -1, n_capteurs)
            )
        for indice, point in enumerate(coordonnees):
            if not isinstance(point, list) or len(point) != 3:
                raise ErreurDonnees(
                    "%s.Accel.sensor_coordinates[%d] (%s) doit contenir 3 "
                    "coordonnées XYZ." % (excitation, indice, noms[indice])
                )
            _valider_vecteur(
                point,
                "%s.Accel.sensor_coordinates[%d] (%s)"
                % (excitation, indice, noms[indice]),
            )

        vitesses = accel["Data_3rdOctave_Vel"]
        if not isinstance(vitesses, list) or len(vitesses) != n_capteurs:
            raise ErreurDonnees(
                "%s.Accel.Data_3rdOctave_Vel : %d lignes pour %d capteurs."
                % (excitation, len(vitesses) if isinstance(vitesses, list)
                   else -1, n_capteurs)
            )
        for indice, ligne in enumerate(vitesses):
            _valider_vecteur(
                ligne,
                "%s.Accel.Data_3rdOctave_Vel[%d] (%s)"
                % (excitation, indice, noms[indice]),
                n_frequences,
            )

        _valider_vecteur(
            micro["frq_3rdOctave"], "%s.Micro.frq_3rdOctave" % excitation
        )
        _valider_vecteur(
            micro["Data_3rdOctave_Lw"],
            "%s.Micro.Data_3rdOctave_Lw" % excitation,
            len(micro["frq_3rdOctave"]),
        )
        if not _est_nombre_fini(micro["Data_GlobalLevel_Lw"]):
            raise ErreurDonnees(
                "%s.Micro.Data_GlobalLevel_Lw n'est pas un nombre fini."
                % excitation
            )
        if len(micro["frq_3rdOctave"]) != n_frequences:
            raise ErreurDonnees(
                "%s : %d fréquences côté Accel et %d côté Micro."
                % (excitation, n_frequences, len(micro["frq_3rdOctave"]))
            )

        if noms_reference is None:
            noms_reference = list(map(str, noms))
            frequences_reference = list(map(float, frequences))
        else:
            if list(map(str, noms)) != noms_reference:
                raise ErreurDonnees(
                    "%s : la liste des capteurs diffère de celle de %s. "
                    "Les capteurs doivent être identiques d'une excitation à "
                    "l'autre." % (excitation, excitations[0])
                )
            if list(map(float, frequences)) != frequences_reference:
                raise ErreurDonnees(
                    "%s : les tiers d'octave diffèrent de ceux de %s."
                    % (excitation, excitations[0])
                )

    if len(noms_reference) < n_capteurs_min:
        raise ErreurDonnees(
            "Le fichier contient %d capteurs, or la combinaison initiale en "
            "demande %d." % (len(noms_reference), n_capteurs_min)
        )

    return {
        "excitations": excitations,
        "capteurs": noms_reference,
        "frequences": frequences_reference,
    }


# ---------------------------------------------------------------------------
# Accès aux données d'une excitation
# ---------------------------------------------------------------------------

def donnees_accel(donnees, excitation):
    """Renvoie (noms, coordonnées, niveaux vibratoires) d'une excitation.

    Les niveaux sont indexés [capteur][fréquence], comme dans le fichier.
    """
    accel = donnees[excitation]["Accel"]
    return (
        [str(nom) for nom in accel["sensor_name"]],
        [[float(valeur) for valeur in point]
         for point in accel["sensor_coordinates"]],
        [[float(valeur) for valeur in ligne]
         for ligne in accel["Data_3rdOctave_Vel"]],
    )


def donnees_micro(donnees, excitation):
    """Renvoie (fréquences, spectre acoustique, niveau global acoustique).

    Ces données sont recopiées telles quelles dans les fichiers de résultats.
    """
    micro = donnees[excitation]["Micro"]
    return (
        [float(valeur) for valeur in micro["frq_3rdOctave"]],
        [float(valeur) for valeur in micro["Data_3rdOctave_Lw"]],
        float(micro["Data_GlobalLevel_Lw"]),
    )


def indices_capteurs_disponibles(noms_capteurs, capteurs_exclus=None):
    """Renvoie les indices des capteurs utilisables pour la sélection.

    Les capteurs listés dans config.CAPTEURS_EXCLUS (capteurs défaillants) sont
    retirés. Un nom exclu absent du fichier est signalé comme une erreur de
    saisie plutôt qu'ignoré silencieusement.
    """
    exclus = list(config.CAPTEURS_EXCLUS if capteurs_exclus is None
                  else capteurs_exclus)
    inconnus = [nom for nom in exclus if nom not in noms_capteurs]
    if inconnus:
        raise ErreurDonnees(
            "CAPTEURS_EXCLUS : capteur(s) inconnu(s) dans le fichier de "
            "mesures : %s" % ", ".join(map(str, inconnus))
        )
    ensemble_exclus = set(exclus)
    return [indice for indice, nom in enumerate(noms_capteurs)
            if nom not in ensemble_exclus]


# ---------------------------------------------------------------------------
# Écriture des résultats
# ---------------------------------------------------------------------------

def construire_metadonnees(methode, resume, graine_effective, extra=None):
    """Assemble le bloc de métadonnées joint aux fichiers de résultats."""
    metadonnees = {
        "methode": methode,
        "date_execution": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fichier_source": os.path.abspath(config.FICHIER_ENTREE),
        "nb_tests": config.Nb_Test,
        "nb_excitations": len(resume["excitations"]),
        "excitations": list(resume["excitations"]),
        "nb_capteurs_fichier": len(resume["capteurs"]),
        "nb_frequences": len(resume["frequences"]),
        "graine_aleatoire": graine_effective,
        "graine_config": config.RANDOM_SEED,
        "capteurs_exclus": list(config.CAPTEURS_EXCLUS),
        "parametres": {
            "S": config.S,
            "S0": config.S0,
            "ZC": config.ZC,
            "ZC0": config.ZC0,
            "W0": config.W0,
            "Sigma_Ref": config.Sigma_Ref,
            "CapteursCommuns": config.CapteursCommuns,
            "Excitations_RF": list(config.Excitations_RF),
            "MAX_TENTATIVES_PAR_TEST": config.MAX_TENTATIVES_PAR_TEST,
            "SEUIL_ECART_DB": config.SEUIL_ECART_DB,
        },
    }
    if extra:
        metadonnees.update(extra)
    return metadonnees


def ecrire_resultats(chemin, cle_racine, tests, metadonnees):
    """Écrit un fichier de résultats {cle_racine: {TESTx: ...}, Metadata: ...}."""
    contenu = {cle_racine: tests, "Metadata": metadonnees}
    dossier = os.path.dirname(os.path.abspath(chemin))
    if dossier and not os.path.isdir(dossier):
        os.makedirs(dossier, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as flux:
        json.dump(contenu, flux, ensure_ascii=False, indent=2)
    return os.path.abspath(chemin)


def lire_resultats(chemin):
    """Relit un fichier de résultats produit par main1.py ou main2.py.

    Renvoie (clé racine, dictionnaire des tests, métadonnées).
    """
    if not os.path.isfile(chemin):
        raise ErreurDonnees("Fichier de résultats introuvable : %s" % chemin)
    with open(chemin, "r", encoding="utf-8") as flux:
        contenu = json.load(flux)
    racines = [cle for cle in contenu if str(cle).startswith("DataISO7849_")]
    if len(racines) != 1:
        raise ErreurDonnees(
            "%s : une clé racine DataISO7849_x est attendue, %d trouvée(s)."
            % (chemin, len(racines))
        )
    cle_racine = racines[0]
    return cle_racine, contenu[cle_racine], contenu.get("Metadata", {})


def trier_tests(tests):
    """Trie les clés TESTx par numéro croissant."""
    motif = re.compile(r"^TEST(\d+)$")
    couples = []
    for cle in tests:
        correspondance = motif.match(str(cle))
        if correspondance:
            couples.append((int(correspondance.group(1)), cle))
    couples.sort(key=lambda couple: couple[0])
    return [cle for _, cle in couples]
