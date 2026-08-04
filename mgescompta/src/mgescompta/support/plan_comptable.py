"""Règles du plan comptable SYCEBNL -- porté depuis App\\Support\\PlanComptable
du projet cger (packages/shared/src/plan-comptable.ts à l'origine)."""
from __future__ import annotations

NATURE_LABELS: dict[str, str] = {
    "CAPITAUX": "Capitaux propres",
    "IMMOBILISATION": "Immobilisations",
    "STOCK": "Stocks",
    "RESULTAT_BILAN": "Résultat (bilan)",
    "CAISSE": "Trésorerie",
    "CHARGE": "Charges",
    "PRODUIT": "Produits",
    "RESULTAT_GESTION": "Résultat (gestion)",
    "AMORTISSEMENT_PROVISION": "Amortissements & provisions",
}

# Suggestion de nature par défaut selon la classe SYCEBNL -- modifiable par l'utilisateur.
NATURE_PAR_DEFAUT_SELON_CLASSE: dict[int, str] = {
    1: "CAPITAUX",
    2: "IMMOBILISATION",
    3: "STOCK",
    4: "RESULTAT_BILAN",
    5: "CAISSE",
    6: "CHARGE",
    7: "PRODUIT",
    8: "RESULTAT_GESTION",
    9: "AMORTISSEMENT_PROVISION",
}

REPORT_A_NOUVEAU_LABELS: dict[str, str] = {
    "SOLDE_COMPTE": "Solde du compte",
    "ECRITURES_NON_LETTREES": "Écritures non lettrées",
}


def report_a_nouveau_par_defaut(classe: int) -> str:
    """Les comptes de tiers (classe 4) se reportent par écritures non
    lettrées, les autres par solde global."""
    return "ECRITURES_NON_LETTREES" if classe == 4 else "SOLDE_COMPTE"


# Plan de démarrage pour une mutuelle de santé (activité courante : collecte
# des cotisations des adhérents, prise en charge de leurs frais de santé,
# fonctionnement du siège). Comptes feuilles du référentiel SYCEBNL -- même
# principe que PlanComptable::COMPTES_DEMARRAGE_RAPIDE dans cger, adapté au
# métier de la mutualité plutôt qu'à une coopérative agricole.
COMPTES_MUTUELLE_SANTE: list[str] = [
    # Capitaux propres
    "112000",  # Réserves statutaires ou contractuelles
    "121000",  # Report à nouveau des excédents
    "129000",  # Report à nouveau des déficits
    "128000",  # Résultat net en instance d'affectation
    # Immobilisations (siège de la mutuelle)
    "244100",  # Matériel et mobilier de bureau
    "244200",  # Matériel informatique et bureautique
    "284400",  # Amortissements du matériel et du mobilier
    # Tiers
    "401100",  # Fournisseurs
    "411000",  # Adhérents (membres de la mutuelle, cotisations à recevoir)
    "421100",  # Personnel, avances
    "422000",  # Personnel, rémunérations dues
    "431100",  # Prestations familiales (charges sociales à payer)
    "432100",  # Caisse de retraite obligatoire
    "442100",  # Impôts et taxes d'État
    "447200",  # Impôts sur salaires
    # Trésorerie
    "521100",  # Banques en monnaie nationale
    "571000",  # Caisse en monnaie nationale
    # Charges de fonctionnement
    "605200",  # Fournitures non stockables - Électricité
    "605500",  # Fournitures de bureau non stockables
    "618100",  # Voyages et déplacements (visites terrain, sensibilisation adhérents)
    "622600",  # Fermages et loyers du foncier (loyer du siège)
    "624100",  # Entretien et réparation des biens immobiliers
    "624200",  # Entretien et réparation des biens mobiliers
    "628100",  # Frais de téléphone
    "641300",  # Taxes sur appointements et salaires
    "652000",  # Subventions accordées par l'entité (prestations/secours versés aux adhérents)
    "661100",  # Appointements salaires et commissions
    "664100",  # Charges sociales sur rémunération du personnel national
    "668500",  # Assurances et organismes de santé (couverture santé du personnel)
    # Produits
    "701000",  # Cotisations des adhérents (recette principale de la mutuelle)
    "704100",  # Dons
    "711000",  # Subventions d'exploitation versées par l'État et les Collectivités publiques
    "713000",  # Subventions d'exploitation versées par les organismes nationaux et internationaux
    "774700",  # Revenus des dépôts à terme et opérations assimilées (placement des réserves)
]
