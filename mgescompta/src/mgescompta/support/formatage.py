"""Formatage des montants : devise de l'application = FCFA, séparateur de
milliers = espace, jamais de décimales (le FCFA n'a pas de sous-unité
utilisée en pratique)."""
from __future__ import annotations


def formater_montant(valeur: float | int | str | None) -> str:
    try:
        entier = round(float(valeur or 0))
    except (TypeError, ValueError):
        entier = 0
    return f"{entier:,}".replace(",", " ") + " FCFA"
