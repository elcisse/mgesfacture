"""Dialogue de création/modification d'une région."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class RegionDialog(QDialog):
    """region_id=None -> création ; sinon -> modification de la région existante."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, region_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.region_id = region_id
        self.setWindowTitle("Modifier la région" if region_id else "Nouvelle région")
        self.resize(360, 150)

        self.champ_code = QLineEdit(self)
        self.champ_nom = QLineEdit(self)
        if region_id is not None:
            self._charger(region_id)

        formulaire = QFormLayout()
        formulaire.addRow("Code :", self.champ_code)
        formulaire.addRow("Nom :", self.champ_nom)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if region_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

    def _charger(self, region_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare("SELECT code, nom FROM region WHERE id = ?")
        query.addBindValue(region_id)
        query.exec()
        if query.next():
            self.champ_code.setText(query.value(0))
            self.champ_nom.setText(query.value(1))

    def _valider(self) -> None:
        code = self.champ_code.text().strip()
        nom = self.champ_nom.text().strip()
        if not code or not nom:
            QMessageBox.warning(self, "Champs manquants", "Le code et le nom sont obligatoires.")
            return

        query = QSqlQuery(self.db)
        if self.region_id is None:
            query.prepare("INSERT INTO region (code, nom) VALUES (?, ?)")
        else:
            query.prepare("UPDATE region SET code = ?, nom = ? WHERE id = ?")
        query.addBindValue(code)
        query.addBindValue(nom)
        if self.region_id is not None:
            query.addBindValue(self.region_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer la région :\n{query.lastError().text()}")
            return

        self.accept()
