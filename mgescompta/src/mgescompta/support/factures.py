"""Comptabilisation et règlement des factures fournisseurs. Une facture est
d'abord enregistrée (document commercial), puis « comptabilisée » (crée
l'opération de constatation de la dette), puis réglée -- en une ou plusieurs
fois -- sans jamais repasser par la saisie manuelle d'écritures."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtSql import QSqlDatabase, QSqlQuery

COMPTE_CAISSE = "571000"
COMPTE_BANQUE = "521100"

# Mode de paiement détaillé -> (compte de trésorerie, code journal) réels.
# Le mode reste purement descriptif/traçabilité : chèque, virement et
# mobile money passent tous par le compte/journal "banque" existant, plutôt
# que d'ajouter de nouveaux comptes comptables non demandés.
MODES_PAIEMENT: dict[str, tuple[str, str]] = {
    "ESPECES": (COMPTE_CAISSE, "CA"),
    "CHEQUE": (COMPTE_BANQUE, "BQ"),
    "VIREMENT": (COMPTE_BANQUE, "BQ"),
    "MOBILE_MONEY": (COMPTE_BANQUE, "BQ"),
}


class FactureInvalideError(Exception):
    pass


@dataclass
class ResultatFacture:
    operation_id: int
    libelle: str


def comptabiliser_facture(db: QSqlDatabase, facture_id: int) -> ResultatFacture:
    """Constate la dette envers le fournisseur (DEBIT compte_charge / CREDIT
    compte_collectif du tiers) pour le montant total de la facture. Journal
    ACHATS. N'est possible qu'une seule fois par facture."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT f.tiers_id, f.numero_facture, f.date_facture, f.compte_charge, f.libelle, "
        "f.montant, f.operation_constat_id, t.intitule, t.compte_collectif "
        "FROM factures f JOIN plan_tiers t ON t.id = f.tiers_id WHERE f.id = ?"
    )
    query.addBindValue(facture_id)
    query.exec()
    if not query.next():
        raise FactureInvalideError("Facture introuvable.")

    (tiers_id, numero_facture, date_facture, compte_charge, libelle_facture, montant,
     operation_constat_id, tiers_intitule, compte_collectif) = (query.value(i) for i in range(9))

    if operation_constat_id:
        # NB: QSqlQuery.value() renvoie '' (pas None) pour un NULL entier
        # avec ce pilote -- test de vérité plutôt que "is not None".
        raise FactureInvalideError("Cette facture est déjà comptabilisée.")

    journal_query = QSqlQuery(db)
    journal_query.exec("SELECT id FROM code_journaux WHERE type = 'ACHATS' ORDER BY id LIMIT 1")
    if not journal_query.next():
        raise FactureInvalideError("Aucun journal de type Achats configuré.")
    journal_id = journal_query.value(0)

    libelle = f"Facture {numero_facture} — {tiers_intitule}"
    if libelle_facture:
        libelle = f"{libelle} — {libelle_facture}"

    db.transaction()
    op_insert = QSqlQuery(db)
    op_insert.prepare(
        "INSERT INTO operations_comptables (journal_id, date, libelle, piece_reference, statut, tiers_id) "
        "VALUES (?, ?, ?, ?, 'VALIDEE', ?)"
    )
    op_insert.addBindValue(journal_id)
    op_insert.addBindValue(date_facture)
    op_insert.addBindValue(libelle)
    op_insert.addBindValue(numero_facture)
    op_insert.addBindValue(tiers_id)
    if not op_insert.exec():
        db.rollback()
        raise FactureInvalideError(f"Échec de création de l'opération : {op_insert.lastError().text()}")
    operation_id = op_insert.lastInsertId()

    ec_insert = QSqlQuery(db)
    ec_insert.prepare(
        "INSERT INTO ecritures_comptables (operation_id, date, libelle, compte, montant, sens, statut) "
        "VALUES (?, ?, ?, ?, ?, ?, 'VALIDEE')"
    )
    for compte, sens in ((compte_charge, "DEBIT"), (compte_collectif, "CREDIT")):
        ec_insert.addBindValue(operation_id)
        ec_insert.addBindValue(date_facture)
        ec_insert.addBindValue(libelle)
        ec_insert.addBindValue(compte)
        ec_insert.addBindValue(montant)
        ec_insert.addBindValue(sens)
        if not ec_insert.exec():
            db.rollback()
            raise FactureInvalideError(f"Échec de création de l'écriture : {ec_insert.lastError().text()}")

    update_facture = QSqlQuery(db)
    update_facture.prepare("UPDATE factures SET operation_constat_id = ? WHERE id = ?")
    update_facture.addBindValue(operation_id)
    update_facture.addBindValue(facture_id)
    if not update_facture.exec():
        db.rollback()
        raise FactureInvalideError(f"Échec de mise à jour de la facture : {update_facture.lastError().text()}")

    db.commit()
    return ResultatFacture(operation_id=operation_id, libelle=libelle)


def factures_a_regler(db: QSqlDatabase, tiers_id: int) -> list[dict]:
    """Factures comptabilisées et pas encore soldées de ce tiers, triées de
    la plus ancienne à la plus récente -- ordre naturel pour une répartition
    FIFO d'un règlement groupé (un seul chèque pour plusieurs factures)."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT id, numero_facture, date_facture, montant, montant_regle FROM factures "
        "WHERE tiers_id = ? AND operation_constat_id IS NOT NULL AND statut != 'SOLDEE' "
        "ORDER BY date_facture, id"
    )
    query.addBindValue(tiers_id)
    query.exec()
    factures = []
    while query.next():
        montant, montant_regle = query.value(3), query.value(4)
        factures.append(
            {
                "id": query.value(0),
                "numero_facture": query.value(1),
                "date_facture": query.value(2),
                "montant": montant,
                "montant_regle": montant_regle,
                "solde": round(montant - montant_regle, 2),
            }
        )
    return factures


def repartir_fifo(factures: list[dict], montant_total: float) -> dict[int, float]:
    """Répartit montant_total sur les factures dans l'ordre (la plus
    ancienne d'abord), jusqu'à épuisement. Si montant_total dépasse la somme
    des soldes, le reliquat n'est affecté à aucune facture -- ce n'est pas
    une erreur, il reste en crédit sur le compte du tiers."""
    allocations: dict[int, float] = {}
    reste = round(montant_total, 2)
    for facture in factures:
        if reste <= 0:
            break
        montant_applique = min(facture["solde"], reste)
        if montant_applique > 0:
            allocations[facture["id"]] = round(montant_applique, 2)
            reste = round(reste - montant_applique, 2)
    return allocations


def reglement_groupe_tiers(
    db: QSqlDatabase,
    tiers_id: int,
    allocations: dict[int, float],
    montant_total: float,
    mode_paiement: str,
    date: str,
    banque_operateur: str | None = None,
    numero_compte: str | None = None,
    reference_paiement: str | None = None,
) -> ResultatFacture:
    """Règle en une fois plusieurs factures d'un même tiers -- typiquement un
    seul chèque, dont le montant peut être inférieur (répondre partiellement,
    au choix, plusieurs factures) ou supérieur (le surplus reste en crédit
    sur le compte du tiers, sans notion d'avance séparée à modéliser) à la
    somme des factures réglées. Une seule écriture est créée pour le montant
    TOTAL du chèque (DEBIT compte_collectif / CREDIT trésorerie) -- cohérente
    quelle que soit la répartition, puisque le grand livre ne se soucie que
    du total encaissé/décaissé."""
    if montant_total is None or montant_total <= 0:
        raise FactureInvalideError("Le montant du règlement doit être supérieur à zéro.")

    allocations = {fid: m for fid, m in allocations.items() if m and m > 0}
    if not allocations:
        raise FactureInvalideError("Sélectionnez au moins une facture à régler.")

    total_alloue = round(sum(allocations.values()), 2)
    if total_alloue > round(montant_total, 2) + 0.001:
        raise FactureInvalideError("Le total réparti sur les factures dépasse le montant du chèque.")

    tiers_query = QSqlQuery(db)
    tiers_query.prepare("SELECT intitule, compte_collectif FROM plan_tiers WHERE id = ?")
    tiers_query.addBindValue(tiers_id)
    tiers_query.exec()
    if not tiers_query.next():
        raise FactureInvalideError("Tiers introuvable.")
    tiers_intitule, compte_collectif = tiers_query.value(0), tiers_query.value(1)

    if mode_paiement not in MODES_PAIEMENT:
        raise FactureInvalideError("Le mode de paiement est obligatoire.")
    compte_tresorerie, code_journal = MODES_PAIEMENT[mode_paiement]

    journal_query = QSqlQuery(db)
    journal_query.prepare("SELECT id FROM code_journaux WHERE type = 'TRESORERIE' AND code = ?")
    journal_query.addBindValue(code_journal)
    journal_query.exec()
    if not journal_query.next():
        raise FactureInvalideError(f"Aucun journal de trésorerie « {code_journal} » configuré.")
    journal_id = journal_query.value(0)

    details_factures = {}
    for facture_id, montant in allocations.items():
        f_query = QSqlQuery(db)
        f_query.prepare(
            "SELECT numero_facture, montant, montant_regle, operation_constat_id, tiers_id "
            "FROM factures WHERE id = ?"
        )
        f_query.addBindValue(facture_id)
        f_query.exec()
        if not f_query.next():
            raise FactureInvalideError(f"Facture {facture_id} introuvable.")
        numero_facture, montant_facture, montant_regle, operation_constat_id, tid = (
            f_query.value(i) for i in range(5)
        )
        if tid != tiers_id:
            raise FactureInvalideError(f"La facture {numero_facture} n'appartient pas à ce tiers.")
        if not operation_constat_id:
            # NB: QSqlQuery.value() renvoie '' (pas None) pour un NULL entier.
            raise FactureInvalideError(f"La facture {numero_facture} n'est pas comptabilisée.")
        solde = round(montant_facture - montant_regle, 2)
        if montant > solde + 0.001:
            raise FactureInvalideError(
                f"Le montant appliqué à la facture {numero_facture} ({montant:.2f}) "
                f"dépasse son solde ({solde:.2f})."
            )
        details_factures[facture_id] = (numero_facture, montant_facture, montant_regle)

    numeros = ", ".join(details_factures[fid][0] for fid in allocations)
    libelle = f"Règlement groupé — {tiers_intitule} ({numeros})"

    db.transaction()
    op_insert = QSqlQuery(db)
    op_insert.prepare(
        "INSERT INTO operations_comptables "
        "(journal_id, date, libelle, piece_reference, statut, tiers_id, "
        "mode_paiement, banque_operateur, numero_compte, reference_paiement) "
        "VALUES (?, ?, ?, ?, 'VALIDEE', ?, ?, ?, ?, ?)"
    )
    op_insert.addBindValue(journal_id)
    op_insert.addBindValue(date)
    op_insert.addBindValue(libelle)
    op_insert.addBindValue(None)
    op_insert.addBindValue(tiers_id)
    op_insert.addBindValue(mode_paiement)
    op_insert.addBindValue(banque_operateur or None)
    op_insert.addBindValue(numero_compte or None)
    op_insert.addBindValue(reference_paiement or None)
    if not op_insert.exec():
        db.rollback()
        raise FactureInvalideError(f"Échec de création de l'opération : {op_insert.lastError().text()}")
    operation_id = op_insert.lastInsertId()

    ec_insert = QSqlQuery(db)
    ec_insert.prepare(
        "INSERT INTO ecritures_comptables (operation_id, date, libelle, compte, montant, sens, statut) "
        "VALUES (?, ?, ?, ?, ?, ?, 'VALIDEE')"
    )
    for compte, sens in ((compte_collectif, "DEBIT"), (compte_tresorerie, "CREDIT")):
        ec_insert.addBindValue(operation_id)
        ec_insert.addBindValue(date)
        ec_insert.addBindValue(libelle)
        ec_insert.addBindValue(compte)
        ec_insert.addBindValue(round(montant_total, 2))
        ec_insert.addBindValue(sens)
        if not ec_insert.exec():
            db.rollback()
            raise FactureInvalideError(f"Échec de création de l'écriture : {ec_insert.lastError().text()}")

    for facture_id, montant in allocations.items():
        numero_facture, montant_facture, montant_regle = details_factures[facture_id]
        nouveau_montant_regle = round(montant_regle + montant, 2)
        nouveau_statut = "SOLDEE" if nouveau_montant_regle >= montant_facture - 0.001 else "PARTIELLEMENT_REGLEE"
        update_facture = QSqlQuery(db)
        update_facture.prepare("UPDATE factures SET montant_regle = ?, statut = ? WHERE id = ?")
        update_facture.addBindValue(nouveau_montant_regle)
        update_facture.addBindValue(nouveau_statut)
        update_facture.addBindValue(facture_id)
        if not update_facture.exec():
            db.rollback()
            raise FactureInvalideError(
                f"Échec de mise à jour de la facture {numero_facture} : {update_facture.lastError().text()}"
            )

    db.commit()
    return ResultatFacture(operation_id=operation_id, libelle=libelle)


def garde_facture_comptabilisee(db: QSqlDatabase, facture_id: int) -> str | None:
    """Bloque la modification/suppression d'une facture déjà comptabilisée
    (les écritures créées ne doivent pas devenir incohérentes avec elle)."""
    query = QSqlQuery(db)
    query.prepare("SELECT operation_constat_id FROM factures WHERE id = ?")
    query.addBindValue(facture_id)
    query.exec()
    if query.next() and query.value(0):
        return "Cette facture est déjà comptabilisée : elle ne peut plus être modifiée ni supprimée."
    return None


def reglement_facture(
    db: QSqlDatabase,
    facture_id: int,
    montant: float,
    mode_paiement: str,
    date: str,
    banque_operateur: str | None = None,
    numero_compte: str | None = None,
    reference_paiement: str | None = None,
) -> ResultatFacture:
    """Règle tout ou partie d'une facture déjà comptabilisée (DEBIT
    compte_collectif du tiers / CREDIT trésorerie). Met à jour le montant
    réglé et le statut de la facture. mode_paiement: une des clés de
    MODES_PAIEMENT (ESPECES, CHEQUE, VIREMENT, MOBILE_MONEY)."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT f.tiers_id, f.numero_facture, f.montant, f.montant_regle, f.operation_constat_id, "
        "t.intitule, t.compte_collectif "
        "FROM factures f JOIN plan_tiers t ON t.id = f.tiers_id WHERE f.id = ?"
    )
    query.addBindValue(facture_id)
    query.exec()
    if not query.next():
        raise FactureInvalideError("Facture introuvable.")

    (tiers_id, numero_facture, montant_total, montant_regle, operation_constat_id,
     tiers_intitule, compte_collectif) = (query.value(i) for i in range(7))

    if not operation_constat_id:
        raise FactureInvalideError("Comptabilisez d'abord la facture avant de la régler.")

    solde = round(montant_total - montant_regle, 2)
    if montant is None or montant <= 0:
        raise FactureInvalideError("Le montant du règlement doit être supérieur à zéro.")
    if montant > solde + 0.001:
        raise FactureInvalideError(f"Le montant dépasse le solde restant dû ({solde:.2f}).")

    if mode_paiement not in MODES_PAIEMENT:
        raise FactureInvalideError("Le mode de paiement est obligatoire.")
    compte_tresorerie, code_journal = MODES_PAIEMENT[mode_paiement]

    journal_query = QSqlQuery(db)
    journal_query.prepare("SELECT id FROM code_journaux WHERE type = 'TRESORERIE' AND code = ?")
    journal_query.addBindValue(code_journal)
    journal_query.exec()
    if not journal_query.next():
        raise FactureInvalideError(f"Aucun journal de trésorerie « {code_journal} » configuré.")
    journal_id = journal_query.value(0)

    libelle = f"Règlement facture {numero_facture} — {tiers_intitule}"

    db.transaction()
    op_insert = QSqlQuery(db)
    op_insert.prepare(
        "INSERT INTO operations_comptables "
        "(journal_id, date, libelle, piece_reference, statut, tiers_id, "
        "mode_paiement, banque_operateur, numero_compte, reference_paiement) "
        "VALUES (?, ?, ?, ?, 'VALIDEE', ?, ?, ?, ?, ?)"
    )
    op_insert.addBindValue(journal_id)
    op_insert.addBindValue(date)
    op_insert.addBindValue(libelle)
    op_insert.addBindValue(numero_facture)
    op_insert.addBindValue(tiers_id)
    op_insert.addBindValue(mode_paiement)
    op_insert.addBindValue(banque_operateur or None)
    op_insert.addBindValue(numero_compte or None)
    op_insert.addBindValue(reference_paiement or None)
    if not op_insert.exec():
        db.rollback()
        raise FactureInvalideError(f"Échec de création de l'opération : {op_insert.lastError().text()}")
    operation_id = op_insert.lastInsertId()

    ec_insert = QSqlQuery(db)
    ec_insert.prepare(
        "INSERT INTO ecritures_comptables (operation_id, date, libelle, compte, montant, sens, statut) "
        "VALUES (?, ?, ?, ?, ?, ?, 'VALIDEE')"
    )
    for compte, sens in ((compte_collectif, "DEBIT"), (compte_tresorerie, "CREDIT")):
        ec_insert.addBindValue(operation_id)
        ec_insert.addBindValue(date)
        ec_insert.addBindValue(libelle)
        ec_insert.addBindValue(compte)
        ec_insert.addBindValue(montant)
        ec_insert.addBindValue(sens)
        if not ec_insert.exec():
            db.rollback()
            raise FactureInvalideError(f"Échec de création de l'écriture : {ec_insert.lastError().text()}")

    nouveau_montant_regle = round(montant_regle + montant, 2)
    nouveau_statut = "SOLDEE" if nouveau_montant_regle >= montant_total - 0.001 else "PARTIELLEMENT_REGLEE"
    update_facture = QSqlQuery(db)
    update_facture.prepare("UPDATE factures SET montant_regle = ?, statut = ? WHERE id = ?")
    update_facture.addBindValue(nouveau_montant_regle)
    update_facture.addBindValue(nouveau_statut)
    update_facture.addBindValue(facture_id)
    if not update_facture.exec():
        db.rollback()
        raise FactureInvalideError(f"Échec de mise à jour de la facture : {update_facture.lastError().text()}")

    db.commit()
    return ResultatFacture(operation_id=operation_id, libelle=libelle)
