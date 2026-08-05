"""Indicateurs clés pour le tableau de bord : trésorerie, factures
fournisseurs à régler, répartition des charges santé/fonctionnement,
opérations en attente de validation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtSql import QSqlDatabase, QSqlQuery

from mgescompta.support.factures import COMPTE_BANQUE, COMPTE_CAISSE

# Convention déjà en place côté factures/import (voir support/factures.py,
# support/import_factures.py) : 652000 = prestations de santé remboursées.
COMPTE_CHARGE_SANTE = "652000"


@dataclass
class Indicateurs:
    solde_caisse: float = 0.0
    solde_banque: float = 0.0
    nb_factures_a_regler: int = 0
    montant_factures_a_regler: float = 0.0
    nb_echeances_depassees: int = 0
    montant_echeances_depassees: float = 0.0
    montant_charges_sante: float = 0.0
    montant_charges_fonctionnement: float = 0.0
    nb_operations_en_attente: int = 0
    montant_operations_en_attente: float = 0.0


def _solde_compte(db: QSqlDatabase, numero_compte: str) -> float:
    """Solde d'un compte de trésorerie (DEBIT - CREDIT), uniquement sur les
    écritures d'opérations validées -- une opération encore en attente ne
    doit pas fausser le solde réel disponible."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT COALESCE(SUM(CASE WHEN e.sens = 'DEBIT' THEN e.montant ELSE -e.montant END), 0) "
        "FROM ecritures_comptables e "
        "JOIN operations_comptables o ON o.id = e.operation_id "
        "WHERE e.compte = ? AND o.statut = 'VALIDEE'"
    )
    query.addBindValue(numero_compte)
    query.exec()
    return query.value(0) if query.next() else 0.0


def calculer_indicateurs(db: QSqlDatabase) -> Indicateurs:
    indicateurs = Indicateurs()

    indicateurs.solde_caisse = _solde_compte(db, COMPTE_CAISSE)
    indicateurs.solde_banque = _solde_compte(db, COMPTE_BANQUE)

    q2 = QSqlQuery(db)
    q2.exec(
        "SELECT COUNT(*), COALESCE(SUM(montant - montant_regle), 0) FROM factures "
        "WHERE operation_constat_id IS NOT NULL AND statut != 'SOLDEE'"
    )
    if q2.next():
        indicateurs.nb_factures_a_regler = q2.value(0)
        indicateurs.montant_factures_a_regler = q2.value(1)

    q3 = QSqlQuery(db)
    q3.prepare(
        "SELECT COUNT(*), COALESCE(SUM(montant - montant_regle), 0) FROM factures "
        "WHERE operation_constat_id IS NOT NULL AND statut != 'SOLDEE' "
        "AND date_echeance IS NOT NULL AND date_echeance < ?"
    )
    q3.addBindValue(date.today().isoformat())
    q3.exec()
    if q3.next():
        indicateurs.nb_echeances_depassees = q3.value(0)
        indicateurs.montant_echeances_depassees = q3.value(1)

    q4 = QSqlQuery(db)
    q4.prepare(
        "SELECT COALESCE(SUM(CASE WHEN e.compte = ? THEN e.montant ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN e.compte != ? THEN e.montant ELSE 0 END), 0) "
        "FROM ecritures_comptables e "
        "JOIN operations_comptables o ON o.id = e.operation_id "
        "JOIN plan_comptable c ON c.numero = e.compte "
        "WHERE c.nature = 'CHARGE' AND e.sens = 'DEBIT' AND o.statut = 'VALIDEE'"
    )
    q4.addBindValue(COMPTE_CHARGE_SANTE)
    q4.addBindValue(COMPTE_CHARGE_SANTE)
    q4.exec()
    if q4.next():
        indicateurs.montant_charges_sante = q4.value(0)
        indicateurs.montant_charges_fonctionnement = q4.value(1)

    q5 = QSqlQuery(db)
    q5.exec(
        "SELECT COUNT(DISTINCT o.id), COALESCE(SUM(e.montant), 0) "
        "FROM operations_comptables o "
        "JOIN ecritures_comptables e ON e.operation_id = o.id AND e.sens = 'DEBIT' "
        "WHERE o.statut = 'EN_ATTENTE'"
    )
    if q5.next():
        indicateurs.nb_operations_en_attente = q5.value(0)
        indicateurs.montant_operations_en_attente = q5.value(1)

    return indicateurs
