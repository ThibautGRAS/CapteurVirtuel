# -*- coding: utf-8 -*-
"""Sélection des capteurs (phase 1) de la méthode Cristofori_Mucchi.

Copie autonome de la logique ISO 7849-2 avec favorisation spatiale (module
selection_capteurs.py du dossier parent), SANS modification du comportement.
La boucle des tests (generer_combinaisons_finales) est remplacée par
pipeline.py, car la phase 2 peut imposer de relancer la sélection.

Ce module implémente la phase 1 (détermination de la combinaison finale d'un
test). Il est strictement identique pour les deux méthodes : la seule
différence est le nombre de capteurs de la combinaison initiale, passé en
argument (5 pour ISO 7849-1, 10 pour ISO 7849-2, valeurs de config.py).

Principe d'un test :

1. tirage d'une combinaison initiale de n_init capteurs, aléatoire mais
   favorisant la dispersion spatiale ;
2. parcours des excitations dans l'ordre numérique ; pour chacune, tant que le
   critère max/min n'est pas satisfait, ajout d'UN capteur supplémentaire
   (les capteurs déjà retenus ne sont jamais retirés) ;
3. la combinaison obtenue après la dernière excitation est la combinaison
   finale du test ;
4. si elle partage trop de capteurs avec une combinaison finale déjà retenue,
   ou si le critère n'a pas pu être satisfait avec les capteurs disponibles,
   le test est intégralement recommencé avec une nouvelle combinaison
   initiale.
"""

from __future__ import annotations

import math
import random
from itertools import combinations as _combinations

import config


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CritereInatteignable(Exception):
    """Tous les capteurs disponibles sont sélectionnés, critère non satisfait.

    Signale que la combinaison initiale tirée ne peut pas mener à une
    combinaison finale valide : le test doit être recommencé.
    """


class SelectionImpossible(Exception):
    """Le nombre de combinaisons finales demandé n'a pas pu être obtenu."""


# ---------------------------------------------------------------------------
# Générateur aléatoire
# ---------------------------------------------------------------------------

def creer_generateur(graine=None):
    """Crée le générateur aléatoire et renvoie (générateur, graine effective).

    Avec config.RANDOM_SEED = None, une graine est tirée au hasard : le
    comportement reste non reproductible d'une exécution à l'autre, mais la
    graine réellement utilisée est enregistrée dans les métadonnées, ce qui
    permet de rejouer une exécution à l'identique en la recopiant dans
    config.RANDOM_SEED.
    """
    graine_config = config.RANDOM_SEED if graine is None else graine
    if graine_config is None:
        graine_effective = random.SystemRandom().randrange(2 ** 32)
    else:
        graine_effective = int(graine_config)
    return random.Random(graine_effective), graine_effective


# ---------------------------------------------------------------------------
# Tirage spatialement dispersé
# ---------------------------------------------------------------------------

def _distance2(point_a, point_b):
    """Carré de la distance euclidienne entre deux points XYZ."""
    return ((point_a[0] - point_b[0]) ** 2
            + (point_a[1] - point_b[1]) ** 2
            + (point_a[2] - point_b[2]) ** 2)


def _tirage_pondere(candidats, poids, generateur):
    """Tire un candidat avec une probabilité proportionnelle à son poids.

    Si tous les poids sont nuls (capteurs superposés), le tirage devient
    uniforme : la sélection reste aléatoire en toute circonstance.
    """
    total = sum(poids)
    if total <= 0.0:
        return generateur.choice(candidats)
    seuil = generateur.random() * total
    cumul = 0.0
    for candidat, poids_candidat in zip(candidats, poids):
        cumul += poids_candidat
        if cumul >= seuil:
            return candidat
    return candidats[-1]


def choisir_capteur_supplementaire(coordonnees, indices_disponibles,
                                   indices_selectionnes, generateur):
    """Choisit UN capteur supplémentaire, aléatoire, à dispersion favorisée.

    La probabilité de tirage d'un capteur candidat est proportionnelle au carré
    de sa distance au capteur déjà sélectionné le plus proche. Un capteur
    éloigné de la combinaison courante est donc très probable, un capteur
    voisin d'un capteur déjà retenu reste possible : la sélection n'est pas
    déterministe, et le coût de calcul reste linéaire en nombre de candidats.
    """
    candidats = [indice for indice in indices_disponibles
                 if indice not in indices_selectionnes]
    if not candidats:
        raise CritereInatteignable(
            "Aucun capteur disponible restant : tous les capteurs utilisables "
            "sont déjà sélectionnés."
        )
    if not indices_selectionnes:
        return generateur.choice(candidats)
    poids = []
    for candidat in candidats:
        distance_min = min(
            _distance2(coordonnees[candidat], coordonnees[retenu])
            for retenu in indices_selectionnes
        )
        poids.append(distance_min)
    return _tirage_pondere(candidats, poids, generateur)


def selection_initiale(coordonnees, indices_disponibles, n_init, generateur):
    """Tire la combinaison initiale de n_init capteurs distincts.

    Le premier capteur est tiré uniformément, les suivants par tirage pondéré
    par le carré de la distance aux capteurs déjà retenus. Le résultat est donc
    aléatoire, différent à chaque test, et spatialement bien réparti.
    """
    if n_init < 1:
        raise ValueError("Le nombre de capteurs initiaux doit être positif.")
    if len(indices_disponibles) < n_init:
        raise ValueError(
            "Combinaison initiale de %d capteurs demandée, mais seulement %d "
            "capteurs disponibles (capteurs exclus déduits)."
            % (n_init, len(indices_disponibles))
        )
    selection = []
    for _ in range(n_init):
        selection.append(
            choisir_capteur_supplementaire(
                coordonnees, indices_disponibles, selection, generateur
            )
        )
    return selection


# ---------------------------------------------------------------------------
# Critère maximum / minimum
# ---------------------------------------------------------------------------

def ecarts_par_bande(niveaux_vel, indices_combinaison):
    """Renvoie (écarts, maxima, minima) par tiers d'octave.

    Pour chaque bande j : max_global_j et min_global_j sur les capteurs de la
    combinaison, puis écart_j = max_global_j - min_global_j.
    """
    if not indices_combinaison:
        raise ValueError("Critère max/min demandé sur une combinaison vide.")
    n_bandes = len(niveaux_vel[indices_combinaison[0]])
    maxima, minima, ecarts = [], [], []
    for bande in range(n_bandes):
        valeurs = [niveaux_vel[indice][bande] for indice in indices_combinaison]
        maximum = max(valeurs)
        minimum = min(valeurs)
        maxima.append(maximum)
        minima.append(minimum)
        ecarts.append(maximum - minimum)
    return ecarts, maxima, minima


def mode_seuil_fixe():
    """Vrai lorsque le critère repose sur un seuil en dB au lieu de n."""
    return config.SEUIL_ECART_DB is not None


def seuil_critere(n_capteurs, facteur=1.0):
    """Seuil auquel les écarts sont comparés.

    Règle normative : le seuil vaut `facteur` x n, où n est le nombre de
    capteurs de la combinaison. Le facteur vient de la norme appliquée :
    2 pour ISO/TS 7849-1 (7.3, "double the number of positions"), 1 pour
    ISO/TS 7849-2 (7.3, "the number of positions").

    Si config.SEUIL_ECART_DB est renseigné, ce seuil fixe en dB remplace la
    règle normative (dérogation explicite, tracée dans les métadonnées).
    """
    if config.SEUIL_ECART_DB is None:
        return float(facteur) * float(n_capteurs)
    return float(config.SEUIL_ECART_DB)


def critere_satisfait(ecarts, n_capteurs, facteur=1.0):
    """Vrai si écart_j < seuil sur TOUS les tiers d'octave."""
    seuil = seuil_critere(n_capteurs, facteur)
    return all(ecart < seuil for ecart in ecarts)


# ---------------------------------------------------------------------------
# Faisabilité
# ---------------------------------------------------------------------------

def diagnostic_faisabilite(niveaux_vel_par_excitation, indices_disponibles,
                           facteur=1.0):
    """Vérifie que le critère max/min peut être satisfait par une combinaison.

    Règle normative (écart_j < n) : l'écart max/min ne peut que croître quand
    des capteurs sont ajoutés, alors que le seuil ne gagne qu'une unité par
    capteur ajouté. Si, avec la totalité des capteurs disponibles, l'écart
    reste supérieur ou égal à leur nombre sur au moins une bande, alors aucune
    combinaison ne peut satisfaire le critère : tous les tirages échoueront.

    Seuil fixe en dB : ce raisonnement ne s'applique pas, car ce sont les
    petites combinaisons qui sont les plus favorables. La faisabilité dépend
    alors du tirage et s'estime avec `taux_acceptation_initiale`.

    Renvoie un dictionnaire : faisable, écart maximal, bandes et excitations
    en cause.
    """
    n_total = len(indices_disponibles)
    seuil = seuil_critere(n_total, facteur)
    bloquantes = []
    ecart_maximal = 0.0
    for nom_excitation, niveaux_vel in niveaux_vel_par_excitation.items():
        ecarts, _, _ = ecarts_par_bande(niveaux_vel, indices_disponibles)
        for bande, ecart in enumerate(ecarts):
            ecart_maximal = max(ecart_maximal, ecart)
            if ecart >= seuil:
                bloquantes.append((nom_excitation, bande, ecart))
    if mode_seuil_fixe():
        # Aucune conclusion d'impossibilité générale n'est possible dans ce
        # mode : seul l'écart maximal est renvoyé, à titre indicatif.
        return {
            "faisable": True,
            "n_capteurs_disponibles": n_total,
            "seuil": seuil,
            "ecart_maximal": ecart_maximal,
            "bandes_bloquantes": [],
            "mode": "seuil_fixe",
        }
    return {
        "faisable": not bloquantes,
        "n_capteurs_disponibles": n_total,
        "seuil": seuil,
        "ecart_maximal": ecart_maximal,
        "bandes_bloquantes": bloquantes,
        "mode": "normatif",
    }


def taux_acceptation_initiale(niveaux_vel_par_excitation, coordonnees,
                              indices_disponibles, n_init, generateur,
                              n_essais=200, facteur=1.0):
    """Estime la proportion de tirages initiaux satisfaisant le critère.

    Utile en mode seuil fixe : un taux nul annonce que tous les tests
    échoueront, un taux faible annonce de nombreux redémarrages. Le tirage est
    simulé sur un générateur indépendant pour ne pas consommer la séquence
    aléatoire de l'étude.
    """
    acceptes = 0
    ecart_minimal = None
    for _ in range(n_essais):
        tirage = selection_initiale(coordonnees, indices_disponibles, n_init,
                                    generateur)
        pire = 0.0
        for niveaux_vel in niveaux_vel_par_excitation.values():
            ecarts, _, _ = ecarts_par_bande(niveaux_vel, tirage)
            pire = max(pire, max(ecarts))
        if ecart_minimal is None or pire < ecart_minimal:
            ecart_minimal = pire
        if pire < seuil_critere(n_init, facteur):
            acceptes += 1
    return {
        "taux": acceptes / float(n_essais),
        "essais": n_essais,
        "meilleur_ecart": ecart_minimal,
    }


def borne_indicative_nb_tests(n_disponibles, n_init,
                              proportion_commune=None):
    """Ordre de grandeur du nombre de combinaisons finales distinctes possibles.

    Deux combinaisons ne peuvent pas partager plus de `proportion_commune` de
    la plus petite des deux. En prenant des combinaisons de taille n_init (cas
    le plus favorable, aucune addition de capteur), chaque nouvelle combinaison
    mobilise au moins n_init - floor(p * n_init) capteurs qui lui sont propres,
    d'où une borne supérieure par simple comptage. Cette borne est indicative :
    les combinaisons réelles sont souvent plus grandes, donc plus nombreuses.
    """
    proportion = (config.CapteursCommuns if proportion_commune is None
                  else proportion_commune)
    communs_max = int(math.floor(proportion * n_init))
    propres = max(1, n_init - communs_max)
    borne_paquet = n_disponibles // propres
    try:
        borne_tirages = len(list(_combinations(range(min(n_disponibles, 24)),
                                               min(n_init, 12))))
    except (ValueError, MemoryError):
        borne_tirages = None
    if n_disponibles <= 24 and n_init <= 12:
        nb_combinaisons = borne_tirages
    else:
        nb_combinaisons = None  # très grand, non calculé
    return {
        "borne_paquet": borne_paquet,
        "capteurs_propres_par_test": propres,
        "capteurs_communs_max": communs_max,
        "nb_combinaisons_initiales": nb_combinaisons,
    }


# ---------------------------------------------------------------------------
# Comparaison des combinaisons finales
# ---------------------------------------------------------------------------

def capteurs_communs(combinaison_a, combinaison_b):
    """Nombre de capteurs communs à deux combinaisons (ordre indifférent)."""
    return len(set(combinaison_a) & set(combinaison_b))


def est_doublon(combinaison, combinaisons_precedentes, proportion=None):
    """Teste si une combinaison finale est un doublon d'une précédente.

    La comparaison est indépendante de l'ordre. Deux combinaisons sont
    considérées comme trop proches si elles partagent plus de
    `proportion` x taille de la PLUS PETITE des deux.

    Renvoie (doublon, index de la combinaison en cause, capteurs communs).
    """
    proportion = (config.CapteursCommuns if proportion is None else proportion)
    ensemble = set(combinaison)
    for indice, precedente in enumerate(combinaisons_precedentes):
        communs = len(ensemble & set(precedente))
        taille_min = min(len(ensemble), len(set(precedente)))
        limite = math.floor(proportion * taille_min)
        if communs > limite:
            return True, indice, communs
    return False, None, 0


# ---------------------------------------------------------------------------
# Phase 1 : construction d'une combinaison finale
# ---------------------------------------------------------------------------

def traiter_excitation(niveaux_vel, coordonnees, indices_disponibles,
                       combinaison, generateur, journal=None,
                       etiquette="", facteur=1.0):
    """Applique le critère max/min pour une excitation.

    Ajoute des capteurs un par un tant que le critère n'est pas satisfait.
    Modifie et renvoie la liste `combinaison` (les capteurs déjà présents sont
    conservés). Lève CritereInatteignable si les capteurs disponibles sont
    épuisés.
    """
    ajouts = []
    while True:
        n_capteurs = len(combinaison)
        ecarts, maxima, minima = ecarts_par_bande(niveaux_vel, combinaison)
        bande_pire = max(range(len(ecarts)), key=lambda j: ecarts[j])
        if journal:
            journal(
                "    %s : n=%d, ecart max=%.1f dB (bande %d, max=%.1f, "
                "min=%.1f), seuil=%.1f"
                % (etiquette, n_capteurs, ecarts[bande_pire], bande_pire + 1,
                   maxima[bande_pire], minima[bande_pire],
                   seuil_critere(n_capteurs, facteur))
            )
        if critere_satisfait(ecarts, n_capteurs, facteur):
            return combinaison, ajouts
        if mode_seuil_fixe():
            # Avec un seuil fixe en dB, l'écart max/min ne peut que croître
            # quand un capteur est ajouté : la combinaison courante est sans
            # issue, il faut repartir d'un autre tirage.
            raise CritereInatteignable(
                "%s : ecart %.1f dB pour un seuil fixe de %.1f dB ; ajouter un "
                "capteur ne peut qu'augmenter l'écart."
                % (etiquette, ecarts[bande_pire],
                   seuil_critere(n_capteurs, facteur))
            )
        nouveau = choisir_capteur_supplementaire(
            coordonnees, indices_disponibles, combinaison, generateur
        )
        combinaison.append(nouveau)
        ajouts.append(nouveau)
        if journal:
            journal("    %s : ajout du capteur d'indice %d (n=%d)"
                    % (etiquette, nouveau, len(combinaison)))


def construire_combinaison_finale(excitations, niveaux_vel_par_excitation,
                                  coordonnees, indices_disponibles, n_init,
                                  generateur, journal=None, noms_capteurs=None,
                                  facteur=1.0):
    """Phase 1 complète pour un test : de la combinaison initiale à la finale.

    La combinaison traverse toutes les excitations dans l'ordre numérique et
    s'enrichit au fil des excitations. La combinaison obtenue après la dernière
    excitation est la combinaison finale.

    Renvoie (combinaison finale, combinaison initiale, ajouts par excitation).
    """
    def nommer(indices):
        if noms_capteurs is None:
            return list(indices)
        return [noms_capteurs[indice] for indice in indices]

    combinaison = selection_initiale(
        coordonnees, indices_disponibles, n_init, generateur
    )
    initiale = list(combinaison)
    if journal:
        journal("  Combinaison initiale (%d capteurs) : %s"
                % (len(initiale), ", ".join(map(str, nommer(initiale)))))

    ajouts_par_excitation = {}
    for excitation in excitations:
        _, ajouts = traiter_excitation(
            niveaux_vel_par_excitation[excitation], coordonnees,
            indices_disponibles, combinaison, generateur, journal=journal,
            etiquette=excitation, facteur=facteur,
        )
        ajouts_par_excitation[excitation] = list(ajouts)

    return combinaison, initiale, ajouts_par_excitation
