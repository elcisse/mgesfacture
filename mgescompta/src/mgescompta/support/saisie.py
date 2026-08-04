"""Résout un modèle de saisie + les valeurs saisies par l'utilisateur en une
opération comptable équilibrée -- porté depuis App\\Actions\\CreerSaisieDepuisModele
et App\\Support\\OperationBalance de cger, simplifié pour une appli
mono-entreprise (pas d'op_id, lignes FIXE/TRESORERIE uniquement)."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtSql import QSqlDatabase, QSqlQuery

COMPTE_CAISSE = "571000"
COMPTE_BANQUE = "521100"


class SaisieInvalideError(Exception):
    pass


@dataclass
class ResultatSaisie:
    operation_id: int
    libelle: str


def creer_operation_depuis_modele(
    db: QSqlDatabase,
    modele_code: str,
    date: str,
    montant: float,
    mode_paiement: str | None = None,  # "CAISSE" ou "BANQUE"
    tiers_id: int | None = None,
    libelle_complement: str | None = None,
    piece_reference: str | None = None,
) -> ResultatSaisie:
    query = QSqlQuery(db)
    query.prepare(
        "SELECT id, nom, journal_type, necessite_mode_paiement FROM modeles_saisie "
        "WHERE code = ? AND actif = 1"
    )
    query.addBindValue(modele_code)
    query.exec()
    if not query.next():
        raise SaisieInvalideError(f"Modèle de saisie inconnu ou inactif : {modele_code}.")
    modele_id, nom, journal_type, necessite_mode_paiement = (
        query.value(0), query.value(1), query.value(2), bool(query.value(3))
    )

    if montant is None or montant <= 0:
        raise SaisieInvalideError("Le montant doit être supérieur à zéro.")

    compte_tresorerie = None
    journal_id = None
    if necessite_mode_paiement:
        if mode_paiement not in ("CAISSE", "BANQUE"):
            raise SaisieInvalideError("Le mode de paiement (caisse ou banque) est obligatoire pour ce modèle.")
        compte_tresorerie = COMPTE_BANQUE if mode_paiement == "BANQUE" else COMPTE_CAISSE
        code_journal = "BQ" if mode_paiement == "BANQUE" else "CA"
        jq = QSqlQuery(db)
        jq.prepare("SELECT id FROM code_journaux WHERE type = 'TRESORERIE' AND code = ?")
        jq.addBindValue(code_journal)
        jq.exec()
        if jq.next():
            journal_id = jq.value(0)

    if journal_id is None:
        jq = QSqlQuery(db)
        jq.prepare("SELECT id FROM code_journaux WHERE type = ? ORDER BY id LIMIT 1")
        jq.addBindValue(journal_type)
        jq.exec()
        if jq.next():
            journal_id = jq.value(0)

    if journal_id is None:
        raise SaisieInvalideError(f"Aucun journal de type {journal_type} configuré.")

    libelle = nom
    if tiers_id is not None:
        tq = QSqlQuery(db)
        tq.prepare("SELECT intitule FROM plan_tiers WHERE id = ?")
        tq.addBindValue(tiers_id)
        tq.exec()
        if tq.next():
            libelle = f"{libelle} — {tq.value(0)}"
    if libelle_complement:
        libelle = f"{libelle} — {libelle_complement.strip()}"

    lignes_query = QSqlQuery(db)
    lignes_query.prepare(
        "SELECT sens, type_compte, compte_code FROM modeles_saisie_lignes "
        "WHERE modele_id = ? ORDER BY ordre"
    )
    lignes_query.addBindValue(modele_id)
    lignes_query.exec()

    lignes: list[tuple[str, str]] = []  # (compte, sens)
    while lignes_query.next():
        sens, type_compte, compte_code = lignes_query.value(0), lignes_query.value(1), lignes_query.value(2)
        if type_compte == "FIXE":
            compte = compte_code
        elif type_compte == "TRESORERIE":
            if compte_tresorerie is None:
                raise SaisieInvalideError("Mode de paiement requis pour résoudre le compte de trésorerie.")
            compte = compte_tresorerie
        else:
            raise SaisieInvalideError(f"Type de compte non supporté : {type_compte}.")
        lignes.append((compte, sens))

    _verifier_equilibre(lignes, montant)
    _verifier_comptes_existants(db, [c for c, _ in lignes])

    db.transaction()
    op_insert = QSqlQuery(db)
    op_insert.prepare(
        "INSERT INTO operations_comptables (journal_id, date, libelle, piece_reference, statut) "
        "VALUES (?, ?, ?, ?, 'VALIDEE')"
    )
    op_insert.addBindValue(journal_id)
    op_insert.addBindValue(date)
    op_insert.addBindValue(libelle)
    op_insert.addBindValue(piece_reference or None)
    if not op_insert.exec():
        db.rollback()
        raise SaisieInvalideError(f"Échec de création de l'opération : {op_insert.lastError().text()}")
    operation_id = op_insert.lastInsertId()

    ec_insert = QSqlQuery(db)
    ec_insert.prepare(
        "INSERT INTO ecritures_comptables (operation_id, date, libelle, compte, montant, sens, statut) "
        "VALUES (?, ?, ?, ?, ?, ?, 'VALIDEE')"
    )
    for compte, sens in lignes:
        ec_insert.addBindValue(operation_id)
        ec_insert.addBindValue(date)
        ec_insert.addBindValue(libelle)
        ec_insert.addBindValue(compte)
        ec_insert.addBindValue(montant)
        ec_insert.addBindValue(sens)
        if not ec_insert.exec():
            db.rollback()
            raise SaisieInvalideError(f"Échec de création de l'écriture : {ec_insert.lastError().text()}")

    db.commit()
    return ResultatSaisie(operation_id=operation_id, libelle=libelle)


def _verifier_equilibre(lignes: list[tuple[str, str]], montant: float) -> None:
    if len(lignes) < 2:
        raise SaisieInvalideError("Un modèle de saisie doit comporter au moins deux lignes.")
    total_debit = sum(1 for _, sens in lignes if sens == "DEBIT") * round(montant * 100)
    total_credit = sum(1 for _, sens in lignes if sens == "CREDIT") * round(montant * 100)
    if total_debit != total_credit:
        raise SaisieInvalideError(
            f"Opération déséquilibrée : débits = {total_debit / 100:.2f}, crédits = {total_credit / 100:.2f}."
        )


def _verifier_comptes_existants(db: QSqlDatabase, comptes: list[str]) -> None:
    manquants = []
    for compte in set(comptes):
        q = QSqlQuery(db)
        q.prepare("SELECT 1 FROM plan_comptable WHERE numero = ?")
        q.addBindValue(compte)
        q.exec()
        if not q.next():
            manquants.append(compte)
    if manquants:
        raise SaisieInvalideError(
            "Compte(s) inconnu(s) dans le plan comptable : " + ", ".join(manquants) + "."
        )
