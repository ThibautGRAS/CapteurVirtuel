# -*- coding: utf-8 -*-
"""Calculs de la méthode Cristofori_Mucchi (phase 2, rayonnement, incertitudes).

Les formules sont celles du prompt, sans aucune modification :

    Lv_j        = 10 log10( (1/n) sum_i 10^(Lv_i_j/10) )
    Lvib_j      = Lv_j + 10 log10(S/S0) + 10 log10(ZC/ZC0)
    Lvib        = 10 log10( sum_j 10^(Lvib_j/10) )
    delta_mk    = | Lvib - Lac |           (Lac = Data_GlobalLevelMean_Lw)
    SS_m        = sum_j sqrt(|Lac_j - Lvib_j| * Lac_j) / sum_j Lac_j
    sigma_j     = Wac_j / Wvib_j  avec  W = W0 10^(L/10)
    u(Lac_j)    = k sqrt(s_j^2 + s_r0^2)
    u(sigma_j)  = (ln10/10) sigma_j u(Lac_j)

Les vecteurs sont traités avec numpy : tableaux [combinaison][bande].
"""

from __future__ import annotations

import math
from itertools import chain, combinations

import numpy as np

import config


class ErreurCalcul(ValueError):
    """Donnée ou configuration rendant un calcul impossible."""


# ---------------------------------------------------------------------------
# Constantes dérivées de la configuration
# ---------------------------------------------------------------------------

def positions_initiales_table1(S=None, S0=None):
    """Nombre initial de capteurs, tableau 1 de ISO/TS 7849-2 (7.3).

    S < 1 m2 -> 10 ; 1 <= S <= 10 -> 20 ; S > 10 -> 2*S/S0 (arrondi supérieur).
    """
    S = config.S if S is None else S
    S0 = config.S0 if S0 is None else S0
    if S <= 0 or S0 <= 0:
        raise ErreurCalcul("S et S0 doivent être strictement positifs.")
    if S < 1.0:
        return 10
    if S <= 10.0:
        return 20
    return int(math.ceil(2 * S / S0))


def terme_surface_impedance():
    """10 log10(S/S0) + 10 log10(ZC/ZC0), en dB."""
    for nom in ("S", "S0", "ZC", "ZC0"):
        if getattr(config, nom) <= 0:
            raise ErreurCalcul("%s doit être strictement positif dans config.py."
                               % nom)
    return (10.0 * math.log10(config.S / config.S0)
            + 10.0 * math.log10(config.ZC / config.ZC0))


def niveau_global(spectre):
    """Somme énergétique d'un ou plusieurs spectres (dernier axe = bandes)."""
    spectre = np.asarray(spectre, dtype=float)
    return 10.0 * np.log10(np.sum(10.0 ** (spectre / 10.0), axis=-1))


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

def nombre_combinaisons(p, n):
    """Coefficient binomial C(p, n)."""
    return math.comb(p, n)


def generer_combinaisons(p, n):
    """Toutes les combinaisons de n positions parmi p : tableau [K][n]."""
    k = math.comb(p, n)
    plat = np.fromiter(chain.from_iterable(combinations(range(p), n)),
                       dtype=np.int64, count=k * n)
    return plat.reshape(k, n)


def niveaux_combinaisons(niveaux_selection, combis):
    """Lv_j de chaque combinaison : tableau [K][J].

    `niveaux_selection` : [p][J] (Data_3rdOctave_Vel des p capteurs retenus).
    """
    energie = 10.0 ** (np.asarray(niveaux_selection, dtype=float) / 10.0)
    moyenne = energie[combis].mean(axis=1)           # (1/n) somme_i
    return 10.0 * np.log10(moyenne)


def niveaux_vibratoires(lv, terme=None):
    """Lvib_j = Lv_j + 10 log10(S/S0) + 10 log10(ZC/ZC0)."""
    terme = terme_surface_impedance() if terme is None else terme
    return np.asarray(lv, dtype=float) + terme


def indice_similarite(lac_j, lvib_j):
    """Spectral_Similarity_m de chaque combinaison : tableau [K].

    sum_j sqrt(|Lac_j - Lvib_j| * Lac_j) / sum_j Lac_j. Le produit sous la
    racine doit rester positif : un Lac_j négatif rend la formule inexploitable
    et provoque une erreur explicite (aucune correction silencieuse).
    """
    lac_j = np.asarray(lac_j, dtype=float)
    if np.any(lac_j < 0.0):
        bande = int(np.argmax(lac_j < 0.0)) + 1
        raise ErreurCalcul(
            "Spectral_Similarity_m : Lac_j négatif (bande %d, %.2f dB), racine "
            "carrée impossible. La formule n'est pas modifiée automatiquement."
            % (bande, lac_j[bande - 1]))
    somme_lac = float(np.sum(lac_j))
    if somme_lac == 0.0:
        raise ErreurCalcul("Spectral_Similarity_m : somme des Lac_j nulle.")
    ecart = np.abs(lac_j[None, :] - np.asarray(lvib_j, dtype=float))
    return np.sum(np.sqrt(ecart * lac_j[None, :]), axis=1) / somme_lac


def facteur_rayonnement(lac_j, lvib_j):
    """radiation_factor_j = Wac_j / Wvib_j (Wx = W0 10^(Lx/10)) : [K][J]."""
    w0 = config.W0
    wac = w0 * 10.0 ** (np.asarray(lac_j, dtype=float) / 10.0)
    wvib = w0 * 10.0 ** (np.asarray(lvib_j, dtype=float) / 10.0)
    return wac[None, :] / wvib


def evaluer_excitation(niveaux_selection, combis, lac_j, lac_global,
                       terme=None):
    """Lv_j, Lvib_j, Lvib, delta_mk et facteur de rayonnement d'une excitation.

    Renvoie un dictionnaire de tableaux [K][J] ou [K].
    """
    lv = niveaux_combinaisons(niveaux_selection, combis)
    lvib_j = niveaux_vibratoires(lv, terme)
    lvib = niveau_global(lvib_j)
    return {
        "Lv_j": lv,
        "Lvib_j": lvib_j,
        "Lvib": lvib,
        "delta": np.abs(lvib - lac_global),
        "sigma": facteur_rayonnement(lac_j, lvib_j),
    }


# ---------------------------------------------------------------------------
# Incertitudes
# ---------------------------------------------------------------------------

def terme_s_r0(frequence):
    """s_r0 (dB) de la plage de config.INCERTITUDE_TERMES_BANDES de la bande."""
    for f_min, f_max, valeur in config.INCERTITUDE_TERMES_BANDES:
        if f_min <= frequence <= f_max:
            return float(valeur)
    raise ErreurCalcul(
        "Bande %g Hz hors de toutes les plages de INCERTITUDE_TERMES_BANDES "
        "(%s) : ajouter une plage dans config.py. Aucune valeur n'est inventée."
        % (frequence, config.INCERTITUDE_TERMES_BANDES))


def moyenne_energetique_runs(niveaux_runs):
    """Lac_j_mean = 10 log10( (1/R) sum_r 10^(Lac_j_r/10) ) : vecteur [J]."""
    niveaux = np.asarray(niveaux_runs, dtype=float)
    return 10.0 * np.log10(np.mean(10.0 ** (niveaux / 10.0), axis=0))


def ecart_type_runs(niveaux_runs):
    """s_j = sqrt( sum_r (Lac_j_r - Lac_j_mean)^2 / (R-1) ) : vecteur [J].

    Lac_j_mean est la moyenne ÉNERGÉTIQUE (définition du prompt). R >= 2 requis.
    """
    niveaux = np.asarray(niveaux_runs, dtype=float)
    r = niveaux.shape[0]
    if r < 2:
        raise ErreurCalcul(
            "Incertitude sur Lac_j : %d run(s) seulement, R-1 = %d au "
            "dénominateur de s_j. Au moins 2 runs sont nécessaires." % (r, r - 1))
    moyenne = moyenne_energetique_runs(niveaux)
    return np.sqrt(np.sum((niveaux - moyenne[None, :]) ** 2, axis=0) / (r - 1))


def incertitude_lac(niveaux_runs, frequences):
    """u(Lac_j) = k sqrt(s_j^2 + s_r0^2) par bande : vecteur [J]."""
    s_j = ecart_type_runs(niveaux_runs)
    s_r0 = np.array([terme_s_r0(f) for f in frequences])
    return config.INCERTITUDE_FACTEUR_ELARGISSEMENT * np.sqrt(s_j ** 2 + s_r0 ** 2)


def incertitude_facteur_rayonnement(sigma, u_lac):
    """u(sigma_j) = (ln10/10) sigma_j u(Lac_j)."""
    return (math.log(10.0) / 10.0) * np.asarray(sigma) * np.asarray(u_lac)


def moyenne_facteurs_excitations(sigmas, incertitudes=None):
    """Moyenne arithmétique des facteurs de rayonnement sur M excitations.

    Incertitude (GUM) : u(moyenne) = sqrt(sum_m u_m^2) / M.
    `sigmas` : liste de vecteurs [J]. Renvoie (moyenne, incertitude ou None).
    """
    sigmas = np.asarray(sigmas, dtype=float)
    m = sigmas.shape[0]
    moyenne = sigmas.mean(axis=0)
    if incertitudes is None:
        return moyenne, None
    u = np.sqrt(np.sum(np.asarray(incertitudes, dtype=float) ** 2, axis=0)) / m
    return moyenne, u
