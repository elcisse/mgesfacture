"""Catégorisation des fournisseurs (santé vs fonctionnement) et résolution
du compte de charge associé -- fixé une fois pour toutes dans Fichier >
Paramètres…, jamais saisi facture par facture. Exporté avec chaque facture
pour que mgescompta n'ait plus à le deviner à l'import."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery

CATEGORIE_SANTE = "SANTE"
CATEGORIE_FONCTIONNEMENT = "FONCTIONNEMENT"


def categorie_tiers(db: QSqlDatabase, tiers_id: int) -> str:
    """SANTE si le tiers est classifié en prestataire de santé (toute
    classification autre que FRN, ex. hôpitaux/pharmacies) ; FONCTIONNEMENT
    sinon (classification FRN, ou tiers non classifié)."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT c.abrege FROM tiers t LEFT JOIN classification c ON c.id = t.classification_id WHERE t.id = ?"
    )
    query.addBindValue(tiers_id)
    query.exec()
    if query.next():
        abrege = query.value(0)
        if abrege and abrege != "FRN":
            return CATEGORIE_SANTE
    return CATEGORIE_FONCTIONNEMENT


def compte_charge_pour_tiers(db: QSqlDatabase, tiers_id: int) -> str:
    categorie = categorie_tiers(db, tiers_id)
    query = QSqlQuery(db)
    query.prepare("SELECT compte_charge FROM parametres_comptes_charge WHERE categorie = ?")
    query.addBindValue(categorie)
    query.exec()
    if query.next():
        return query.value(0) or ""
    return ""
