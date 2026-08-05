"""Page Tiers : liste + création/modification/suppression."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QWidget

from mgesfacture.support.import_tiers import importer_csv
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

        bouton_importer = QPushButton("Importer depuis mgescompta (CSV)…", self)
        bouton_importer.clicked.connect(self._importer_depuis_mgescompta)
        self.entete_layout.addWidget(bouton_importer)

    def _importer_depuis_mgescompta(self) -> None:
        chemin_str, _ = QFileDialog.getOpenFileName(
            self, "Importer des tiers depuis mgescompta", "", "Fichiers CSV (*.csv)"
        )
        if not chemin_str:
            return

        try:
            resultat = importer_csv(self.db, Path(chemin_str))
        except (OSError, ValueError) as erreur:
            QMessageBox.critical(self, "Erreur", f"Impossible d'importer le fichier :\n{erreur}")
            return

        self.liste.refresh()

        resume = (
            f"{resultat.nb_importes} tiers importé(s).\n"
            f"{resultat.nb_deja_existants} déjà existant(s) (ignoré(s)).\n"
            f"{len(resultat.erreurs)} erreur(s)."
        )
        if resultat.erreurs:
            boite = QMessageBox(self)
            boite.setIcon(QMessageBox.Icon.Warning)
            boite.setWindowTitle("Import terminé avec des erreurs")
            boite.setText(resume)
            boite.setDetailedText(
                "\n".join(f"Ligne {e.numero_ligne} (numéro {e.numero}) : {e.message}" for e in resultat.erreurs)
            )
            boite.exec()
        else:
            QMessageBox.information(self, "Import terminé", resume)
