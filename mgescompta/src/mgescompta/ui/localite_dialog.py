"""Dialogue de création/modification d'une localité (rattachée à un département)."""
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


class LocaliteDialog(QDialog):
    """localite_id=None -> création ; sinon -> modification de la localité existante."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, localite_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.localite_id = localite_id
        self.setWindowTitle("Modifier la localité" if localite_id else "Nouvelle localité")
        self.resize(380, 180)

        self.champ_departement = QComboBox(self)
        self._charger_departements()

        self.champ_nom = QLineEdit(self)
        if localite_id is not None:
            self._charger(localite_id)

        formulaire = QFormLayout()
        formulaire.addRow("Département :", self.champ_departement)
        formulaire.addRow("Nom :", self.champ_nom)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if localite_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

    def _charger_departements(self) -> None:
        query = QSqlQuery(self.db)
        query.exec(
            "SELECT d.id, d.code, d.nom, r.nom FROM departement d "
            "JOIN region r ON r.id = d.region_id ORDER BY r.code, d.code"
        )
        while query.next():
            self.champ_departement.addItem(f"{query.value(1)} — {query.value(2)} ({query.value(3)})", query.value(0))

    def _charger(self, localite_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare("SELECT departement_id, nom FROM localite WHERE id = ?")
        query.addBindValue(localite_id)
        query.exec()
        if query.next():
            index_departement = self.champ_departement.findData(query.value(0))
            if index_departement >= 0:
                self.champ_departement.setCurrentIndex(index_departement)
            self.champ_nom.setText(query.value(1))

    def _valider(self) -> None:
        if self.champ_departement.count() == 0:
            QMessageBox.warning(self, "Aucun département", "Créez d'abord un département.")
            return

        nom = self.champ_nom.text().strip()
        if not nom:
            QMessageBox.warning(self, "Champ manquant", "Le nom est obligatoire.")
            return

        query = QSqlQuery(self.db)
        if self.localite_id is None:
            query.prepare("INSERT INTO localite (departement_id, nom) VALUES (?, ?)")
        else:
            query.prepare("UPDATE localite SET departement_id = ?, nom = ? WHERE id = ?")
        query.addBindValue(self.champ_departement.currentData())
        query.addBindValue(nom)
        if self.localite_id is not None:
            query.addBindValue(self.localite_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer la localité :\n{query.lastError().text()}")
            return

        self.accept()
