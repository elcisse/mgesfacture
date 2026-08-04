"""Page Opérations comptables : liste + création manuelle + validation des
opérations en attente. Les opérations créées via la saisie guidée ou les
dialogues sont désormais validées automatiquement ; ce bouton reste utile
pour les rares opérations laissées « En attente » manuellement. Supprimer une
opération retire l'ensemble de ses écritures (cascade) : toujours équilibré,
puisqu'on retire un ensemble débit/crédit complet."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from mgescompta.ui.listable_page import ListablePage
from mgescompta.ui.operation_apercu_dialog import OperationApercuDialog
from mgescompta.ui.operation_dialog import OperationDialog

COLONNES = {
    "id": "ID",
    "journal_id": "Journal",
    "date": "Date",
    "libelle": "Libellé",
    "statut": "Statut",
}


class OperationsPage(ListablePage):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(
            db, "operations_comptables", "Opérations comptables", COLONNES,
            OperationDialog, "Nouvelle opération…",
            edit_dialog_factory=OperationDialog,
            permettre_suppression=True,
            parent=parent,
        )

        bouton_apercu = QPushButton("Aperçu…", self)
        bouton_apercu.clicked.connect(self._apercu_selection)
        self.entete_layout.addWidget(bouton_apercu)

        bouton_valider = QPushButton("Valider la sélection", self)
        bouton_valider.clicked.connect(self._valider_selection)
        self.entete_layout.addWidget(bouton_valider)

    def _apercu_selection(self) -> None:
        operation_id = self._selection_id()
        if operation_id is None:
            return
        OperationApercuDialog(self.db, self, operation_id).exec()

    def _valider_selection(self) -> None:
        lignes = self.liste.view.selectionModel().selectedRows()
        if not lignes:
            QMessageBox.information(self, "Aucune sélection", "Sélectionnez au moins une opération à valider.")
            return

        colonne_id = self.liste.model.fieldIndex("id")
        colonne_statut = self.liste.model.fieldIndex("statut")

        a_valider = []
        for index in lignes:
            statut = self.liste.model.data(self.liste.model.index(index.row(), colonne_statut))
            if statut == "EN_ATTENTE":
                a_valider.append(self.liste.model.data(self.liste.model.index(index.row(), colonne_id)))

        if not a_valider:
            QMessageBox.information(
                self, "Rien à valider", "Les opérations sélectionnées ne sont pas « En attente »."
            )
            return

        self.db.transaction()
        update_operation = QSqlQuery(self.db)
        update_operation.prepare("UPDATE operations_comptables SET statut = 'VALIDEE' WHERE id = ?")
        update_ecritures = QSqlQuery(self.db)
        update_ecritures.prepare("UPDATE ecritures_comptables SET statut = 'VALIDEE' WHERE operation_id = ?")
        for operation_id in a_valider:
            update_operation.addBindValue(operation_id)
            update_ecritures.addBindValue(operation_id)
            if not update_operation.exec() or not update_ecritures.exec():
                self.db.rollback()
                QMessageBox.critical(
                    self, "Erreur",
                    f"Échec de la validation :\n{update_operation.lastError().text() or update_ecritures.lastError().text()}",
                )
                self.liste.refresh()
                return
        self.db.commit()

        self.liste.refresh()
        QMessageBox.information(self, "Validé", f"{len(a_valider)} opération(s) validée(s).")
