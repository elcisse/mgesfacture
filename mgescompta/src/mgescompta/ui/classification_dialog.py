"""Dialogue de création/modification d'une classification de tiers."""
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


class ClassificationDialog(QDialog):
    """classification_id=None -> création ; sinon -> modification de la ligne existante."""

    def __init__(
        self, db: QSqlDatabase, parent: QWidget | None = None, classification_id: int | None = None
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.classification_id = classification_id
        self.setWindowTitle("Modifier la classification" if classification_id else "Nouvelle classification")
        self.resize(360, 150)

        self.champ_abrege = QLineEdit(self)
        self.champ_libelle = QLineEdit(self)
        if classification_id is not None:
            self._charger(classification_id)

        formulaire = QFormLayout()
        formulaire.addRow("Abrégé :", self.champ_abrege)
        formulaire.addRow("Libellé :", self.champ_libelle)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if classification_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

    def _charger(self, classification_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare("SELECT abrege, libelle FROM classification WHERE id = ?")
        query.addBindValue(classification_id)
        query.exec()
        if query.next():
            self.champ_abrege.setText(query.value(0))
            self.champ_libelle.setText(query.value(1))

    def _valider(self) -> None:
        abrege = self.champ_abrege.text().strip()
        libelle = self.champ_libelle.text().strip()
        if not abrege or not libelle:
            QMessageBox.warning(self, "Champs manquants", "L'abrégé et le libellé sont obligatoires.")
            return

        query = QSqlQuery(self.db)
        if self.classification_id is None:
            query.prepare("INSERT INTO classification (abrege, libelle) VALUES (?, ?)")
            query.addBindValue(abrege)
            query.addBindValue(libelle)
        else:
            query.prepare("UPDATE classification SET abrege = ?, libelle = ? WHERE id = ?")
            query.addBindValue(abrege)
            query.addBindValue(libelle)
            query.addBindValue(self.classification_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Échec de l'enregistrement :\n{query.lastError().text()}")
            return

        self.accept()
