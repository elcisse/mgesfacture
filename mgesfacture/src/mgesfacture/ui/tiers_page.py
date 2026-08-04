"""Page Tiers : liste + création/modification/suppression."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QWidget

from mgesfacture.ui.listable_page import ListablePage
from mgesfacture.ui.tiers_dialog import TiersDialog

COLONNES = {
    "id": "ID",
    "numero": "Numéro",
    "intitule": "Intitulé",
    "type": "Type",
    "compte_collectif": "Compte collectif",
    "classification_id": "Classification",
    "region_id": "Région",
    "departement_id": "Département",
    "localite_id": "Localité",
    "adresse": "Adresse",
    "telephone": "Téléphone",
    "email": "Email",
    "actif": "Actif",
}


def _garde_suppression_tiers(db: QSqlDatabase, tiers_id: int) -> str | None:
    query = QSqlQuery(db)
    query.prepare("SELECT COUNT(*) FROM factures WHERE tiers_id = ?")
    query.addBindValue(tiers_id)
    query.exec()
    query.next()
    if query.value(0):
        return "Ce tiers a des factures enregistrées : il ne peut pas être supprimé (désactivez-le plutôt)."
    return None


class TiersPage(ListablePage):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(
            db, "tiers", "Tiers", COLONNES,
            TiersDialog, "Nouveau tiers…",
            edit_dialog_factory=TiersDialog,
            permettre_suppression=True,
            garde_suppression=_garde_suppression_tiers,
            relations={
                "classification_id": ("classification", "libelle"),
                "region_id": ("region", "nom"),
                "departement_id": ("departement", "nom"),
                "localite_id": ("localite", "nom"),
            },
            tri="numero",
            parent=parent,
        )
