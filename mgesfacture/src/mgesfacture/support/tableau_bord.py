"""Indicateurs clés pour le tableau de bord : activité d'enregistrement,
suivi de l'export vers mgescompta, échéances, fournisseur principal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtSql import QSqlDatabase, QSqlQuery


@dataclass
class Indicateurs:
    nb_factures: int = 0
    montant_total: float = 0.0
    nb_non_exportees: int = 0
    montant_non_exportees: float = 0.0
    nb_echeances_depassees: int = 0
    montant_echeances_depassees: float = 0.0
    top_fournisseur_nom: str | None = None
    top_fournisseur_montant: float = 0.0
    dernier_export: str | None = None


def calculer_indicateurs(db: QSqlDatabase) -> Indicateurs:
    indicateurs = Indicateurs()

    q1 = QSqlQuery(db)
    q1.exec("SELECT COUNT(*), COALESCE(SUM(montant), 0) FROM factures")
    if q1.next():
        indicateurs.nb_factures = q1.value(0)
        indicateurs.montant_total = q1.value(1)

    q2 = QSqlQuery(db)
    q2.exec("SELECT COUNT(*), COALESCE(SUM(montant), 0) FROM factures WHERE exportee_le IS NULL")
    if q2.next():
        indicateurs.nb_non_exportees = q2.value(0)
        indicateurs.montant_non_exportees = q2.value(1)

    q3 = QSqlQuery(db)
    q3.prepare(
        "SELECT COUNT(*), COALESCE(SUM(montant), 0) FROM factures "
        "WHERE date_echeance IS NOT NULL AND date_echeance < ?"
    )
    q3.addBindValue(date.today().isoformat())
    q3.exec()
    if q3.next():
        indicateurs.nb_echeances_depassees = q3.value(0)
        indicateurs.montant_echeances_depassees = q3.value(1)

    q4 = QSqlQuery(db)
    q4.exec(
        "SELECT t.intitule, SUM(f.montant) AS total FROM factures f "
        "JOIN tiers t ON t.id = f.tiers_id "
        "GROUP BY f.tiers_id ORDER BY total DESC LIMIT 1"
    )
    if q4.next():
        indicateurs.top_fournisseur_nom = q4.value(0)
        indicateurs.top_fournisseur_montant = q4.value(1)

    q5 = QSqlQuery(db)
    q5.exec("SELECT MAX(exportee_le) FROM factures")
    if q5.next():
        indicateurs.dernier_export = q5.value(0) or None

    return indicateurs


def periode_disponible(db: QSqlDatabase) -> tuple[str | None, str | None]:
    """Plus ancienne et plus récente date_facture -- pour proposer une plage
    par défaut qui couvre toutes les factures plutôt qu'une plage arbitraire."""
    query = QSqlQuery(db)
    query.exec("SELECT MIN(date_facture), MAX(date_facture) FROM factures")
    if query.next():
        return query.value(0) or None, query.value(1) or None
    return None, None


def montants_par_region(db: QSqlDatabase, date_debut: str | None = None, date_fin: str | None = None) -> list[dict]:
    """Total facturé par région du tiers (date_facture dans [date_debut,
    date_fin], bornes incluses si fournies), régions les plus importantes
    d'abord. Un tiers sans région renseignée est regroupé à part plutôt
    qu'exclu -- le total de la table doit toujours pouvoir se recouper avec
    le montant total du tableau de bord sur la même période."""
    conditions = []
    valeurs = []
    if date_debut:
        conditions.append("f.date_facture >= ?")
        valeurs.append(date_debut)
    if date_fin:
        conditions.append("f.date_facture <= ?")
        valeurs.append(date_fin)
    clause_where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = QSqlQuery(db)
    query.prepare(
        "SELECT COALESCE(r.nom, 'Région non renseignée') AS region_nom, SUM(f.montant) AS total "
        "FROM factures f JOIN tiers t ON t.id = f.tiers_id LEFT JOIN region r ON r.id = t.region_id "
        f"{clause_where} "
        "GROUP BY region_nom ORDER BY total DESC"
    )
    for valeur in valeurs:
        query.addBindValue(valeur)
    query.exec()

    resultats = []
    while query.next():
        resultats.append({"region": query.value(0), "montant": query.value(1)})
    return resultats
