"""Dialogue de création/modification d'un département."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class DepartementDialog(QDialog):
    """departement_id=None -> création ; sinon -> modification du département existant."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, departement_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.departement_id = departement_id
        self.setWindowTitle("Modifier le département" if departement_id else "Nouveau département")
        self.resize(380, 180)

        self.champ_region = QComboBox(self)
        self._charger_regions()

        self.champ_code = QLineEdit(self)
        self.champ_nom = QLineEdit(self)
        if departement_id is not None:
            self._charger(departement_id)

        formulaire = QFormLayout()
        formulaire.addRow("Région :", self.champ_region)
        formulaire.addRow("Code :", self.champ_code)
        formulaire.addRow("Nom :", self.champ_nom)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if departement_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

    def _charger_regions(self) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT id, code, nom FROM region ORDER BY code")
        while query.next():
            self.champ_region.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _charger(self, departement_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare("SELECT region_id, code, nom FROM departement WHERE id = ?")
        query.addBindValue(departement_id)
        query.exec()
        if query.next():
            index_region = self.champ_region.findData(query.value(0))
            if index_region >= 0:
                self.champ_region.setCurrentIndex(index_region)
            self.champ_code.setText(query.value(1))
            self.champ_nom.setText(query.value(2))

    def _valider(self) -> None:
        if self.champ_region.count() == 0:
            QMessageBox.warning(self, "Aucune région", "Créez d'abord une région.")
            return

        code = self.champ_code.text().strip()
        nom = self.champ_nom.text().strip()
        if not code or not nom:
            QMessageBox.warning(self, "Champs manquants", "Le code et le nom sont obligatoires.")
            return

        query = QSqlQuery(self.db)
        if self.departement_id is None:
            query.prepare("INSERT INTO departement (region_id, code, nom) VALUES (?, ?, ?)")
        else:
            query.prepare("UPDATE departement SET region_id = ?, code = ?, nom = ? WHERE id = ?")
        query.addBindValue(self.champ_region.currentData())
        query.addBindValue(code)
        query.addBindValue(nom)
        if self.departement_id is not None:
            query.addBindValue(self.departement_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le département :\n{query.lastError().text()}")
            return

        self.accept()
