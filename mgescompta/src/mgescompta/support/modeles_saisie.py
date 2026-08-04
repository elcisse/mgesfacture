"""Catalogue des modèles de saisie pour une mutuelle de santé -- porte
l'esprit de ModeleSaisie/CreerSaisieDepuisModele de cger, simplifié pour une
appli mono-entreprise : chaque modèle a exactement 2 lignes (débit/crédit
d'un même montant), et les lignes ne référencent que des comptes FIXE ou
TRESORERIE (pas de résolution par tiers -- le tiers, quand il est proposé,
n'enrichit que le libellé, il n'influence pas le compte utilisé).

Pour les catégories achat, vente, personnel, fiscal et cotisation, chaque
opération se fait en deux temps (comptabilité d'engagement) :
- une CONSTATATION reconnaît la dette/créance (aucun mouvement de
  trésorerie) -- journal ACHATS/VENTES/GENERAL selon le cas ;
- un RÈGLEMENT solde ensuite le compte de tiers via la trésorerie -- journal
  TRESORERIE, avec choix caisse/banque.
Les opérations sans dette/créance intermédiaire (remboursement de soins, don,
subvention) restent en une seule étape au comptant.

Objectif : permettre à un employé qui ne connaît pas la comptabilité de
saisir une opération courante sans jamais choisir lui-même un compte ni se
soucier du débit/crédit.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LigneModele:
    ordre: int
    sens: str  # "DEBIT" ou "CREDIT"
    type_compte: str  # "FIXE" ou "TRESORERIE"
    compte_code: str | None  # requis si type_compte == "FIXE"


@dataclass(frozen=True)
class ModeleSaisie:
    code: str
    nom: str
    journal_type: str
    necessite_tiers: str | None  # "ADHERENT", "FOURNISSEUR", "SALARIE" ou None
    necessite_mode_paiement: bool
    ordre_affichage: int
    lignes: tuple[LigneModele, ...]


def _paire(debit_code: str | None, credit_code: str | None) -> tuple[LigneModele, LigneModele]:
    """Construit les 2 lignes d'un modèle. None signifie TRESORERIE (résolu
    au moment de la saisie selon le mode de paiement choisi)."""
    return (
        LigneModele(1, "DEBIT", "FIXE" if debit_code else "TRESORERIE", debit_code),
        LigneModele(2, "CREDIT", "FIXE" if credit_code else "TRESORERIE", credit_code),
    )


MODELES_MUTUELLE_SANTE: list[ModeleSaisie] = [
    # --- Cotisations (constatation puis règlement) ---
    ModeleSaisie(
        "COTIS_CONSTAT", "Cotisation — Facturée à un adhérent", "VENTES", "ADHERENT", False, 10,
        _paire("411000", "701000"),  # Adhérents / Cotisations des adhérents
    ),
    ModeleSaisie(
        "COTIS_REGLEMENT", "Cotisation — Encaissement", "TRESORERIE", "ADHERENT", True, 20,
        _paire(None, "411000"),  # Trésorerie / Adhérents
    ),

    # --- Prise en charge tiers-payant (la mutuelle règle directement le
    # prestataire de santé conventionné, plutôt que de rembourser l'adhérent) ---
    ModeleSaisie(
        "PRISE_CHARGE_CONSTAT", "Prise en charge — Facture reçue d'un prestataire de santé",
        "ACHATS", "FOURNISSEUR", False, 21,
        _paire("652000", "401100"),  # Subventions accordées (prise en charge) / Fournisseurs
    ),
    ModeleSaisie(
        "PRISE_CHARGE_REGLEMENT", "Prise en charge — Règlement au prestataire de santé",
        "TRESORERIE", "FOURNISSEUR", True, 22,
        _paire("401100", None),  # Fournisseurs / Trésorerie
    ),

    # --- Achats (une constatation par type de charge, un règlement commun) ---
    ModeleSaisie(
        "ACHAT_BUREAU_C", "Achat — Fournitures de bureau (facture reçue)", "ACHATS", "FOURNISSEUR", False, 30,
        _paire("605500", "401100"),
    ),
    ModeleSaisie(
        "ACHAT_ELEC_C", "Achat — Électricité (facture reçue)", "ACHATS", "FOURNISSEUR", False, 40,
        _paire("605200", "401100"),
    ),
    ModeleSaisie(
        "ACHAT_TEL_C", "Achat — Téléphone (facture reçue)", "ACHATS", "FOURNISSEUR", False, 50,
        _paire("628100", "401100"),
    ),
    ModeleSaisie(
        "ACHAT_LOYER_C", "Achat — Loyer du siège (facture reçue)", "ACHATS", "FOURNISSEUR", False, 60,
        _paire("622600", "401100"),
    ),
    ModeleSaisie(
        "ACHAT_ENTRETIEN_C", "Achat — Entretien/réparation (facture reçue)", "ACHATS", "FOURNISSEUR", False, 70,
        _paire("624100", "401100"),
    ),
    ModeleSaisie(
        "ACHAT_DEPLACEMENT_C", "Achat — Déplacement/mission (facture ou note de frais)", "ACHATS", "FOURNISSEUR", False, 80,
        _paire("618100", "401100"),
    ),
    ModeleSaisie(
        "ACHAT_REGLEMENT", "Achat — Règlement d'une facture fournisseur", "TRESORERIE", "FOURNISSEUR", True, 90,
        _paire("401100", None),
    ),

    # --- Personnel (salaire et charges sociales, constatation puis règlement) ---
    ModeleSaisie(
        "SALAIRE_CONSTAT", "Personnel — Salaire constaté", "GENERAL", "SALARIE", False, 100,
        _paire("661100", "422000"),
    ),
    ModeleSaisie(
        "SALAIRE_REGLEMENT", "Personnel — Règlement du salaire", "TRESORERIE", "SALARIE", True, 110,
        _paire("422000", None),
    ),
    ModeleSaisie(
        "CHARGES_SOC_CONSTAT", "Personnel — Charges sociales constatées", "GENERAL", None, False, 120,
        _paire("664100", "431100"),
    ),
    ModeleSaisie(
        "CHARGES_SOC_REGLEMENT", "Personnel — Règlement des charges sociales", "TRESORERIE", None, True, 130,
        _paire("431100", None),
    ),

    # --- Fiscal (constatation puis règlement) ---
    ModeleSaisie(
        "FISCAL_CONSTAT", "Fiscal — Impôts et taxes constatés", "GENERAL", None, False, 140,
        _paire("641300", "442100"),
    ),
    ModeleSaisie(
        "FISCAL_REGLEMENT", "Fiscal — Règlement des impôts et taxes", "TRESORERIE", None, True, 150,
        _paire("442100", None),
    ),

    # --- Opérations au comptant (une seule étape, hors périmètre engagement) ---
    ModeleSaisie(
        "REMB_SOINS", "Remboursement de soins versé à un adhérent", "TRESORERIE", "ADHERENT", True, 160,
        _paire("652000", None),
    ),
    ModeleSaisie(
        "DON_RECU", "Don reçu", "TRESORERIE", None, True, 170,
        _paire(None, "704100"),
    ),
    ModeleSaisie(
        "SUBVENTION_RECUE", "Subvention reçue", "TRESORERIE", None, True, 180,
        _paire(None, "713000"),
    ),
]
