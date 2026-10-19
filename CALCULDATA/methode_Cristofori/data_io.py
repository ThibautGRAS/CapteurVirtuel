# -*- coding: utf-8 -*-
"""Lecture, validation et écriture des fichiers JSON (méthode Cristofori_Mucchi).

Seul point de contact avec le disque. Le fichier d'entrée est ouvert en
lecture seule. Les clés utilisées sont celles de DataMesure2_v03 :

* Accel.Data_3rdOctave_Vel            niveaux vibratoires [capteur][bande]
* Micro.Data_3rdOctaveMean_Lw         Lac_j, moyenne sur les runs (par bande)
* Micro.Data_GlobalLevelMean_Lw       Lac, niveau global unique (tous les runs)
* Micro.Data_3rdOctave_Lw             niveaux par run [run][bande] (incertitudes)

Les clés « Mean » de Accel et les niveaux globaux par run ne servent pas aux
calculs. Le bloc BDF n'est jamais traité comme une excitation.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime

import config


class ErreurDonnees(Exception):
    """Structure ou contenu du fichier de mesures invalide."""


_MOTIF_EXCITATION = re.compile(r"^EXCITATION(\d+)$")


def chemin_programme(chemin):
    """Résout un chemin relatif par rapport au dossier du programme."""
    if os.path.isabs(chemin):
        return chemin
    return os.path.join(config.DOSSIER_PROGRAMME, chemin)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def lire_mesures(chemin=None):
    """Lit le fichier de mesures (lecture seule) et renvoie le dictionnaire."""
    chemin = chemin_programme(chemin or config.FICHIER_ENTREE)
    if not os.path.isfile(chemin):
        raise ErreurDonnees(
            "Fichier de mesures introuvable : %s\n"
            "Vérifier config.FICHIER_ENTREE." % chemin
        )
    try:
        with open(chemin, "r", encoding="utf-8") as flux:
            donnees = json.load(flux)
    except json.JSONDecodeError as err:
        raise ErreurDonnees(
            "Le fichier %s n'est pas un JSON valide : %s" % (chemin, err)
        ) from err
    if not isinstance(donnees, dict):
        raise ErreurDonnees("%s : un objet JSON est attendu à la racine." % chemin)
    return donnees


def numero_excitation(nom):
    """Numéro entier d'une clé EXCITATIONx."""
    correspondance = _MOTIF_EXCITATION.match(str(nom))
    if not correspondance:
        raise ErreurDonnees("Nom d'excitation inattendu : %r" % (nom,))
    return int(correspondance.group(1))


def lister_excitations(donnees):
    """Clés EXCITATIONx triées numériquement (BDF et autres clés ignorés)."""
    noms = [cle for cle in donnees if _MOTIF_EXCITATION.match(str(cle))]
    return sorted(noms, key=numero_excitation)


def excitations_a_traiter(donnees, exclues=None):
    """Excitations présentes dans le fichier moins EXCITATIONS_A_EXCLURE.

    Une exclusion qui ne correspond à aucune excitation du fichier est une
    erreur de saisie, signalée explicitement.
    """
    exclues = list(config.EXCITATIONS_A_EXCLURE if exclues is None else exclues)
    toutes = lister_excitations(donnees)
    if not toutes:
        raise ErreurDonnees(
            "Aucune clé EXCITATIONx dans le fichier. Clés présentes : %s"
            % ", ".join(sorted(map(str, donnees)))
        )
    numeros = {numero_excitation(nom) for nom in toutes}
    inconnues = [m for m in exclues if m not in numeros]
    if inconnues:
        raise ErreurDonnees(
            "EXCITATIONS_A_EXCLURE : excitation(s) absente(s) du fichier : %s "
            "(présentes : %s)"
            % (inconnues, sorted(numeros))
        )
    retenues = [nom for nom in toutes if numero_excitation(nom) not in set(exclues)]
    if not retenues:
        raise ErreurDonnees(
            "EXCITATIONS_A_EXCLURE exclut toutes les excitations du fichier."
        )
    return retenues


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _fini(valeur):
    return (isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
            and math.isfinite(float(valeur)))


def _vecteur(valeur, nom, longueur=None):
    if not isinstance(valeur, list):
        raise ErreurDonnees("%s doit être une liste." % nom)
    if longueur is not None and len(valeur) != longueur:
        raise ErreurDonnees("%s : %d valeurs, %d attendues."
                            % (nom, len(valeur), longueur))
    for i, element in enumerate(valeur):
        if not _fini(element):
            raise ErreurDonnees("%s[%d] = %r n'est pas un nombre fini."
                                % (nom, i, element))
    return valeur


def valider_mesures(donnees, excitations):
    """Vérifie les champs utilisés pour les excitations traitées.

    Renvoie un résumé : capteurs, fréquences. Lève ErreurDonnees au premier
    défaut avec un message explicite.
    """
    noms_ref = None
    frequences_ref = None
    for exc in excitations:
        bloc = donnees[exc]
        for sous in ("Accel", "Micro"):
            if not isinstance(bloc.get(sous), dict):
                raise ErreurDonnees("%s : bloc %s absent ou invalide." % (exc, sous))
        accel, micro = bloc["Accel"], bloc["Micro"]
        for champ in ("frq_3rdOctave", "sensor_name", "sensor_coordinates",
                      "Data_3rdOctave_Vel"):
            if champ not in accel:
                raise ErreurDonnees("%s.Accel : champ %s absent." % (exc, champ))
        for champ in ("frq_3rdOctave", "Data_3rdOctave_Lw",
                      "Data_3rdOctaveMean_Lw", "Data_GlobalLevelMean_Lw"):
            if champ not in micro:
                raise ErreurDonnees(
                    "%s.Micro : champ %s absent (fichier de type v03 attendu)."
                    % (exc, champ))

        freq = _vecteur(accel["frq_3rdOctave"], "%s.Accel.frq_3rdOctave" % exc)
        if not freq:
            raise ErreurDonnees("%s.Accel.frq_3rdOctave est vide." % exc)
        nb = len(freq)
        noms = accel["sensor_name"]
        if not isinstance(noms, list) or not noms:
            raise ErreurDonnees("%s.Accel.sensor_name : liste non vide attendue."
                                % exc)
        if len(set(map(str, noms))) != len(noms):
            raise ErreurDonnees("%s.Accel.sensor_name contient des doublons." % exc)
        coord = accel["sensor_coordinates"]
        if not isinstance(coord, list) or len(coord) != len(noms):
            raise ErreurDonnees("%s.Accel.sensor_coordinates : %d entrées pour "
                                "%d capteurs." % (exc, len(coord)
                                                  if isinstance(coord, list) else -1,
                                                  len(noms)))
        for i, point in enumerate(coord):
            if not isinstance(point, list) or len(point) != 3:
                raise ErreurDonnees("%s.Accel.sensor_coordinates[%d] (%s) : 3 "
                                    "coordonnées XYZ attendues." % (exc, i, noms[i]))
            _vecteur(point, "%s.Accel.sensor_coordinates[%d]" % (exc, i))
        vel = accel["Data_3rdOctave_Vel"]
        if not isinstance(vel, list) or len(vel) != len(noms):
            raise ErreurDonnees("%s.Accel.Data_3rdOctave_Vel : %d lignes pour %d "
                                "capteurs." % (exc, len(vel)
                                               if isinstance(vel, list) else -1,
                                               len(noms)))
        for i, ligne in enumerate(vel):
            _vecteur(ligne, "%s.Accel.Data_3rdOctave_Vel[%d] (%s)"
                     % (exc, i, noms[i]), nb)

        _vecteur(micro["frq_3rdOctave"], "%s.Micro.frq_3rdOctave" % exc, nb)
        if [float(x) for x in micro["frq_3rdOctave"]] != [float(x) for x in freq]:
            raise ErreurDonnees("%s : fréquences Accel et Micro différentes." % exc)
        _vecteur(micro["Data_3rdOctaveMean_Lw"], "%s.Micro.Data_3rdOctaveMean_Lw"
                 % exc, nb)
        if not _fini(micro["Data_GlobalLevelMean_Lw"]):
            raise ErreurDonnees("%s.Micro.Data_GlobalLevelMean_Lw : nombre fini "
                                "attendu." % exc)
        runs = micro["Data_3rdOctave_Lw"]
        if not isinstance(runs, list) or not runs:
            raise ErreurDonnees("%s.Micro.Data_3rdOctave_Lw : liste de runs non "
                                "vide attendue." % exc)
        for r, ligne in enumerate(runs):
            _vecteur(ligne, "%s.Micro.Data_3rdOctave_Lw[%d]" % (exc, r), nb)

        if noms_ref is None:
            noms_ref = [str(n) for n in noms]
            frequences_ref = [float(f) for f in freq]
        else:
            if [str(n) for n in noms] != noms_ref:
                raise ErreurDonnees("%s : liste de capteurs différente de %s."
                                    % (exc, excitations[0]))
            if [float(f) for f in freq] != frequences_ref:
                raise ErreurDonnees("%s : tiers d'octave différents de %s."
                                    % (exc, excitations[0]))
    return {"capteurs": noms_ref, "frequences": frequences_ref}


# ---------------------------------------------------------------------------
# Accès aux données d'une excitation
# ---------------------------------------------------------------------------

def donnees_accel(donnees, excitation):
    """(noms, coordonnées, niveaux Data_3rdOctave_Vel [capteur][bande])."""
    accel = donnees[excitation]["Accel"]
    return (
        [str(n) for n in accel["sensor_name"]],
        [[float(v) for v in p] for p in accel["sensor_coordinates"]],
        [[float(v) for v in ligne] for ligne in accel["Data_3rdOctave_Vel"]],
    )


def donnees_micro(donnees, excitation):
    """(Lac_j = Data_3rdOctaveMean_Lw, Lac = Data_GlobalLevelMean_Lw,
    niveaux par run Data_3rdOctave_Lw [run][bande])."""
    micro = donnees[excitation]["Micro"]
    return (
        [float(v) for v in micro["Data_3rdOctaveMean_Lw"]],
        float(micro["Data_GlobalLevelMean_Lw"]),
        [[float(v) for v in ligne] for ligne in micro["Data_3rdOctave_Lw"]],
    )


def indices_capteurs_disponibles(noms_capteurs, exclus=None):
    """Indices des capteurs utilisables (CAPTEURS_EXCLUS retirés)."""
    exclus = list(config.CAPTEURS_EXCLUS if exclus is None else exclus)
    inconnus = [n for n in exclus if n not in noms_capteurs]
    if inconnus:
        raise ErreurDonnees("CAPTEURS_EXCLUS : capteur(s) inconnu(s) : %s"
                            % ", ".join(map(str, inconnus)))
    ensemble = set(exclus)
    return [i for i, n in enumerate(noms_capteurs) if n not in ensemble]


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def parametres_config():
    """Ensemble des paramètres de config.py, pour les métadonnées."""
    parametres = {}
    for nom in dir(config):
        if not nom[0].isupper():
            continue
        valeur = getattr(config, nom)
        if isinstance(valeur, (int, float, str, bool, list, tuple, type(None))):
            parametres[nom] = list(valeur) if isinstance(valeur, tuple) else valeur
    return parametres


def ecrire_resultats(chemin, contenu):
    """Écrit le JSON de résultats (dossiers créés au besoin)."""
    chemin = chemin_programme(chemin)
    dossier = os.path.dirname(chemin)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as flux:
        json.dump(contenu, flux, ensure_ascii=False, indent=2)
    return chemin


def lire_resultats(chemin):
    """Relit un fichier de résultats produit par main.py."""
    chemin = chemin_programme(chemin)
    if not os.path.isfile(chemin):
        raise ErreurDonnees("Fichier de résultats introuvable : %s" % chemin)
    with open(chemin, "r", encoding="utf-8") as flux:
        return json.load(flux)


def horodatage():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
