"""Page CRUD complète de la classification des tiers : créer, modifier, supprimer."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from mgescompta.ui.classification_dialog import ClassificationDialog
from mgescompta.ui.table_page import SqlTablePage

COLONNES = {"id": "ID", "abrege": "Abrégé", "libelle": "Libellé"}


class ClassificationPage(QWidget):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db

        self.liste = SqlTablePage(db, "classification", "", COLONNES, self)
        self.liste.layout().itemAt(0).widget().hide()  # masque le <h2> dupliqué, le titre est dans l'en-tête ci-dessous

        bouton_ajouter = QPushButton("Nouvelle classification…", self)
        bouton_ajouter.clicked.connect(self._creer)

        bouton_modifier = QPushButton("Modifier la sélection", self)
        bouton_modifier.clicked.connect(self._modifier)

        bouton_supprimer = QPushButton("Supprimer la sélection", self)
        bouton_supprimer.clicked.connect(self._supprimer)

        entete = QHBoxLayout()
        entete.addWidget(QLabel("<h2>Classification</h2>"))
        entete.addStretch(1)
        entete.addWidget(bouton_ajouter)
        entete.addWidget(bouton_modifier)
        entete.addWidget(bouton_supprimer)

        layout = QVBoxLayout(self)
        layout.addLayout(entete)
        layout.addWidget(self.liste)

    def _selection_id(self) -> int | None:
        lignes = self.liste.view.selectionModel().selectedRows()
        if not lignes:
            QMessageBox.information(self, "Aucune sélection", "Sélectionnez une classification.")
            return None
        colonne_id = self.liste.model.fieldIndex("id")
        return self.liste.model.data(self.liste.model.index(lignes[0].row(), colonne_id))

    def _creer(self) -> None:
        dialog = ClassificationDialog(self.db, self)
        if dialog.exec():
            self.liste.refresh()

    def _modifier(self) -> None:
        classification_id = self._selection_id()
        if classification_id is None:
            return
        dialog = ClassificationDialog(self.db, self, classification_id=classification_id)
        if dialog.exec():
            self.liste.refresh()

    def _supprimer(self) -> None:
        classification_id = self._selection_id()
        if classification_id is None:
            return

        reponse = QMessageBox.question(
            self,
            "Supprimer la classification",
            "Voulez-vous vraiment supprimer cette classification ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reponse != QMessageBox.StandardButton.Yes:
            return

        query = QSqlQuery(self.db)
        query.prepare("DELETE FROM classification WHERE id = ?")
        query.addBindValue(classification_id)
        if not query.exec():
            QMessageBox.warning(
                self,
                "Suppression impossible",
                "Cette classification est probablement utilisée par un ou plusieurs tiers.\n"
                "Retirez-la de ces tiers avant de la supprimer.",
            )
            return

        self.liste.refresh()

    def refresh(self) -> None:
        self.liste.refresh()
