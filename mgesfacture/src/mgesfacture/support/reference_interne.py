"""Génération de la référence interne des factures : identifiant lisible et
stable (contrairement à numero_facture, saisi par le fournisseur et non
fiable comme identifiant -- il peut se répéter entre tiers ou d'une année
sur l'autre).

Format F-AAAA-NNNNN, compteur remis à zéro chaque année (l'année de
date_facture, cohérent avec annee_mois qui en dérive déjà). Attribuée une
seule fois à la création, jamais régénérée ni modifiée ensuite -- y compris
si date_facture est corrigée après coup lors d'une modification."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery

PREFIXE = "F"


def generer_reference_interne(db: QSqlDatabase, annee: int) -> str:
    prefixe_annee = f"{PREFIXE}-{annee}-"

    query = QSqlQuery(db)
    query.prepare(
        "SELECT reference_interne FROM factures WHERE reference_interne LIKE ? "
        "ORDER BY reference_interne DESC LIMIT 1"
    )
    query.addBindValue(prefixe_annee + "%")
    query.exec()

    if query.next():
        dernier_numero = int(query.value(0).rsplit("-", 1)[-1])
    else:
        dernier_numero = 0

    return f"{prefixe_annee}{dernier_numero + 1:05d}"
