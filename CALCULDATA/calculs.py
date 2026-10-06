# -*- coding: utf-8 -*-
"""Calculs acoustiques et vibratoires des méthodes ISO 7849-1 et ISO 7849-2.

Organisation du module :

* calculs communs aux deux méthodes (moyenne énergétique, niveau global,
  terme de surface et d'impédance) ;
* calculs spécifiques à ISO 7849-1 ;
* calculs spécifiques à ISO 7849-2 (facteur de rayonnement).

Toutes les fonctions travaillent sur des listes de flottants et ne lisent ni
n'écrivent aucun fichier. Les niveaux sont en dB, les fréquences en Hz.
"""

from __future__ import annotations

import math

import config


# ---------------------------------------------------------------------------
# 1. Calculs communs aux deux méthodes
# ---------------------------------------------------------------------------

def moyenne_energetique(niveaux):
    """Moyenne énergétique d'une liste de niveaux en dB.

    L = 10 * log10( (1/n) * somme(10**(Li/10)) )
    """
    if not niveaux:
        raise ValueError("Moyenne énergétique demandée sur une liste vide.")
    somme = sum(10.0 ** (float(niveau) / 10.0) for niveau in niveaux)
    return 10.0 * math.log10(somme / len(niveaux))


def somme_energetique(niveaux):
    """Somme énergétique d'une liste de niveaux en dB.

    L = 10 * log10( somme(10**(Li/10)) )
    """
    if not niveaux:
        raise ValueError("Somme énergétique demandée sur une liste vide.")
    somme = sum(10.0 ** (float(niveau) / 10.0) for niveau in niveaux)
    return 10.0 * math.log10(somme)


def spectre_moyen_vel(niveaux_vel, indices_capteurs):
    """Calcule Data_3rdOctaveMean_Vel pour une combinaison de capteurs.

    `niveaux_vel` est indexé [capteur][fréquence]. Le champ
    Data_3rdOctaveMean_Vel éventuellement présent dans le fichier source n'est
    jamais utilisé : la moyenne est toujours recalculée ici, à partir des seuls
    capteurs de la combinaison passée en argument.
    """
    if not indices_capteurs:
        raise ValueError("Aucun capteur fourni pour la moyenne des niveaux.")
    n_frequences = len(niveaux_vel[indices_capteurs[0]])
    return [
        moyenne_energetique(
            [niveaux_vel[indice][bande] for indice in indices_capteurs]
        )
        for bande in range(n_frequences)
    ]


def positions_initiales_table1(partie, S=None, S0=None):
    """Nombre initial de positions de mesure, tableau 1 de la norme.

    ISO/TS 7849-1, 7.3 : S < 1 m2 -> 5  ; 1 <= S <= 10 -> 10 ; S > 10 -> S/S0
    ISO/TS 7849-2, 7.3 : S < 1 m2 -> 10 ; 1 <= S <= 10 -> 20 ; S > 10 -> 2*S/S0

    Le nombre renvoyé est arrondi à l'entier supérieur pour les grandes
    surfaces. Avec S = 0,369286 m2, le tableau donne 5 (partie 1) et 10
    (partie 2), valeurs de départ des deux méthodes.
    """
    S = config.S if S is None else S
    S0 = config.S0 if S0 is None else S0
    if partie not in (1, 2):
        raise ValueError("Partie de norme inconnue : %r (1 ou 2 attendu)."
                         % (partie,))
    if S <= 0 or S0 <= 0:
        raise ValueError("S et S0 doivent être strictement positifs.")
    facteur = 1 if partie == 1 else 2
    if S < 1.0:
        return 5 * facteur
    if S <= 10.0:
        return 10 * facteur
    return int(math.ceil(facteur * S / S0))


def terme_surface_impedance(S=None, S0=None, ZC=None, ZC0=None):
    """Terme constant 10*log10(S/S0) + 10*log10(ZC/ZC0), en dB.

    Les valeurs par défaut proviennent de config.py.
    """
    S = config.S if S is None else S
    S0 = config.S0 if S0 is None else S0
    ZC = config.ZC if ZC is None else ZC
    ZC0 = config.ZC0 if ZC0 is None else ZC0
    for nom, valeur in (("S", S), ("S0", S0), ("ZC", ZC), ("ZC0", ZC0)):
        if valeur <= 0:
            raise ValueError(
                "%s doit être strictement positif dans config.py (valeur : %r)."
                % (nom, valeur)
            )
    return 10.0 * math.log10(S / S0) + 10.0 * math.log10(ZC / ZC0)


def niveau_global(spectre):
    """Niveau global d'un spectre en tiers d'octave (somme énergétique)."""
    return somme_energetique(spectre)


# ---------------------------------------------------------------------------
# 2. Calculs spécifiques à ISO 7849-1
# ---------------------------------------------------------------------------

def spectre_vib_iso1(spectre_moyen):
    """Data_3rdOctave_Vib selon ISO 7849-1.

    Vib_j = MeanVel_j + 10*log10(S/S0) + 10*log10(ZC/ZC0)
    """
    terme = terme_surface_impedance()
    return [valeur + terme for valeur in spectre_moyen]


# ---------------------------------------------------------------------------
# 3. Calculs spécifiques à ISO 7849-2
# ---------------------------------------------------------------------------

def facteur_rayonnement_excitation(spectre_moyen, spectre_acou, W0=None):
    """Facteur de rayonnement d'une excitation, bande par bande.

    Wvib_j  = W0 * 10**(Vib_j  / 10)      avec Vib_j calculé comme en ISO 7849-1
    Wacou_j = W0 * 10**(Acou_j / 10)
    sigma_j = Wacou_j / Wvib_j

    W0 se simplifie dans le rapport ; il est conservé dans le calcul pour
    rester fidèle à la définition du cahier des charges.
    """
    W0 = config.W0 if W0 is None else W0
    if len(spectre_moyen) != len(spectre_acou):
        raise ValueError(
            "Facteur de rayonnement : %d bandes vibratoires pour %d bandes "
            "acoustiques." % (len(spectre_moyen), len(spectre_acou))
        )
    spectre_vib = spectre_vib_iso1(spectre_moyen)
    facteurs = []
    for vib, acou in zip(spectre_vib, spectre_acou):
        puissance_vib = W0 * 10.0 ** (vib / 10.0)
        puissance_acou = W0 * 10.0 ** (acou / 10.0)
        if puissance_vib <= 0.0:
            raise ValueError(
                "Puissance vibratoire nulle : facteur de rayonnement non "
                "calculable."
            )
        facteurs.append(puissance_acou / puissance_vib)
    return facteurs


def moyenne_facteurs_rayonnement(facteurs_par_excitation):
    """Moyenne ARITHMÉTIQUE, bande par bande, de plusieurs facteurs.

    La moyenne porte sur les grandeurs linéaires (rapports de puissances), pas
    sur leur expression en dB.
    """
    if not facteurs_par_excitation:
        raise ValueError(
            "Aucun facteur de rayonnement à moyenner : vérifier "
            "config.Excitations_RF."
        )
    n_bandes = len(facteurs_par_excitation[0])
    for facteurs in facteurs_par_excitation:
        if len(facteurs) != n_bandes:
            raise ValueError(
                "Les facteurs de rayonnement n'ont pas tous le même nombre de "
                "bandes."
            )
    n_excitations = len(facteurs_par_excitation)
    return [
        sum(facteurs[bande] for facteurs in facteurs_par_excitation)
        / n_excitations
        for bande in range(n_bandes)
    ]


def calculer_facteur_rayonnement(donnees_mesures, excitations, acces_accel,
                                 acces_micro, indices_capteurs,
                                 excitations_rf=None):
    """Facteur de rayonnement global utilisé par ISO 7849-2.

    Calculé UNE SEULE FOIS, avant les tests, à partir de TOUS les capteurs
    disponibles (capteurs exclus mis à part) et des excitations listées dans
    config.Excitations_RF. La valeur obtenue est ensuite réutilisée pour tous
    les tests et toutes les excitations.

    `acces_accel` et `acces_micro` sont les fonctions de data_io qui extraient
    les données d'une excitation ; elles sont passées en argument pour garder
    ce module indépendant des entrées/sorties.

    Renvoie (facteur moyen, détail par excitation utilisée).
    """
    excitations_rf = (list(config.Excitations_RF) if excitations_rf is None
                      else list(excitations_rf))
    if not excitations_rf:
        raise ValueError(
            "config.Excitations_RF est vide : au moins une excitation est "
            "nécessaire pour calculer le facteur de rayonnement."
        )

    correspondance = {}
    for nom in excitations:
        numero = int(str(nom).replace("EXCITATION", ""))
        correspondance[numero] = nom

    detail = {}
    facteurs_par_excitation = []
    for numero in excitations_rf:
        if numero not in correspondance:
            raise ValueError(
                "config.Excitations_RF demande l'excitation %d, absente du "
                "fichier de mesures (excitations disponibles : %s)."
                % (numero, ", ".join(sorted(map(str, correspondance))))
            )
        nom_excitation = correspondance[numero]
        _, _, niveaux_vel = acces_accel(donnees_mesures, nom_excitation)
        _, spectre_acou, _ = acces_micro(donnees_mesures, nom_excitation)
        spectre_moyen = spectre_moyen_vel(niveaux_vel, indices_capteurs)
        facteurs = facteur_rayonnement_excitation(spectre_moyen, spectre_acou)
        facteurs_par_excitation.append(facteurs)
        detail[nom_excitation] = facteurs

    return moyenne_facteurs_rayonnement(facteurs_par_excitation), detail


def spectre_vib_iso2(spectre_moyen, facteur_rayonnement, sigma_ref=None):
    """Data_3rdOctave_Vib selon ISO 7849-2.

    Vib_j = MeanVel_j + 10*log10(S/S0) + 10*log10(ZC/ZC0)
            + 10*log10(sigma_j / Sigma_Ref)
    """
    sigma_ref = config.Sigma_Ref if sigma_ref is None else sigma_ref
    if sigma_ref <= 0:
        raise ValueError(
            "Sigma_Ref doit être strictement positif dans config.py "
            "(valeur : %r)." % (sigma_ref,)
        )
    if len(spectre_moyen) != len(facteur_rayonnement):
        raise ValueError(
            "ISO 7849-2 : %d bandes de niveaux pour %d bandes de facteur de "
            "rayonnement." % (len(spectre_moyen), len(facteur_rayonnement))
        )
    base = spectre_vib_iso1(spectre_moyen)
    spectre = []
    for valeur, sigma in zip(base, facteur_rayonnement):
        if sigma <= 0.0:
            raise ValueError(
                "Facteur de rayonnement nul ou négatif : correction en dB non "
                "calculable."
            )
        spectre.append(valeur + 10.0 * math.log10(sigma / sigma_ref))
    return spectre


# ---------------------------------------------------------------------------
# 4. Assemblage d'un bloc de résultats
# ---------------------------------------------------------------------------

def bloc_excitation(frequences, spectre_acou, global_acou, noms_capteurs,
                    coordonnees, niveaux_vel, indices_combinaison,
                    facteur_rayonnement=None):
    """Construit le bloc de résultats d'une excitation pour un test.

    Avec `facteur_rayonnement=None`, le bloc suit ISO 7849-1. Sinon, le champ
    Data_3rdOctave_Radiation_Factor est ajouté et le niveau vibratoire est
    corrigé selon ISO 7849-2.

    Les données acoustiques sont recopiées sans aucune modification.
    """
    spectre_moyen = spectre_moyen_vel(niveaux_vel, indices_combinaison)
    if facteur_rayonnement is None:
        spectre_vib = spectre_vib_iso1(spectre_moyen)
    else:
        spectre_vib = spectre_vib_iso2(spectre_moyen, facteur_rayonnement)

    bloc = {
        "frq_3rdOctave": list(frequences),
        "Data_3rdOctave_Acou": list(spectre_acou),
        "Data_GlobalLevel_Acou": global_acou,
        "Accel_name": [noms_capteurs[indice] for indice in indices_combinaison],
        "Accel_coordinates": [list(coordonnees[indice])
                              for indice in indices_combinaison],
        "Data_3rdOctave_Vel": [list(niveaux_vel[indice])
                               for indice in indices_combinaison],
        "Data_3rdOctaveMean_Vel": spectre_moyen,
    }
    if facteur_rayonnement is not None:
        bloc["Data_3rdOctave_Radiation_Factor"] = list(facteur_rayonnement)
    bloc["Data_3rdOctave_Vib"] = spectre_vib
    bloc["Data_GlobalLevel_Vib"] = niveau_global(spectre_vib)
    return bloc
