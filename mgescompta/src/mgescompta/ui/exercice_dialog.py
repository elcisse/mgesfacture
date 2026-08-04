"""Dialogue de création/modification d'un exercice comptable."""
from __future__ import annotations

import datetime

from PySide6.QtCore import QDate
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class ExerciceDialog(QDialog):
    """exercice_id=None -> création (libellé/dates suggérés = année civile
    suivant le dernier exercice existant) ; sinon -> modification."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, exercice_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.exercice_id = exercice_id
        self.setWindowTitle("Modifier l'exercice comptable" if exercice_id else "Nouvel exercice comptable")
        self.resize(380, 220)

        annee = self._annee_suggeree()

        self.champ_libelle = QLineEdit(f"Exercice {annee}", self)

        self.champ_date_debut = QDateEdit(QDate(annee, 1, 1), self)
        self.champ_date_debut.setCalendarPopup(True)
        self.champ_date_debut.setDisplayFormat("dd/MM/yyyy")

        self.champ_date_fin = QDateEdit(QDate(annee, 12, 31), self)
        self.champ_date_fin.setCalendarPopup(True)
        self.champ_date_fin.setDisplayFormat("dd/MM/yyyy")

        self.champ_statut = QComboBox(self)
        self.champ_statut.addItem("Ouvert", "OUVERT")
        self.champ_statut.addItem("Clôturé", "CLOTURE")

        formulaire = QFormLayout()
        formulaire.addRow("Libellé :", self.champ_libelle)
        formulaire.addRow("Date de début :", self.champ_date_debut)
        formulaire.addRow("Date de fin :", self.champ_date_fin)
        formulaire.addRow("Statut :", self.champ_statut)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if exercice_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if exercice_id is not None:
            self._charger(exercice_id)

    def _annee_suggeree(self) -> int:
        """Année suivant la fin du dernier exercice existant, ou l'année en
        cours s'il n'y en a aucun (non utilisé en mode modification)."""
        query = QSqlQuery(self.db)
        query.exec("SELECT MAX(date_fin) FROM exercices_comptables")
        if query.next() and query.value(0):
            derniere_fin = datetime.date.fromisoformat(query.value(0))
            return derniere_fin.year + 1
        return datetime.date.today().year

    def _charger(self, exercice_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare("SELECT libelle, date_debut, date_fin, statut FROM exercices_comptables WHERE id = ?")
        query.addBindValue(exercice_id)
        query.exec()
        if query.next():
            self.champ_libelle.setText(query.value(0))
            self.champ_date_debut.setDate(QDate.fromString(query.value(1), "yyyy-MM-dd"))
            self.champ_date_fin.setDate(QDate.fromString(query.value(2), "yyyy-MM-dd"))
            self.champ_statut.setCurrentIndex(self.champ_statut.findData(query.value(3)))

    def _valider(self) -> None:
        libelle = self.champ_libelle.text().strip()
        if not libelle:
            QMessageBox.warning(self, "Libellé manquant", "Le libellé de l'exercice est obligatoire.")
            return

        debut = self.champ_date_debut.date()
        fin = self.champ_date_fin.date()
        if fin <= debut:
            QMessageBox.warning(self, "Dates invalides", "La date de fin doit être postérieure à la date de début.")
            return

        query = QSqlQuery(self.db)
        if self.exercice_id is None:
            query.prepare(
                "INSERT INTO exercices_comptables (libelle, date_debut, date_fin, statut) VALUES (?, ?, ?, ?)"
            )
        else:
            query.prepare(
                "UPDATE exercices_comptables SET libelle = ?, date_debut = ?, date_fin = ?, statut = ? WHERE id = ?"
            )
        query.addBindValue(libelle)
        query.addBindValue(debut.toString("yyyy-MM-dd"))
        query.addBindValue(fin.toString("yyyy-MM-dd"))
        query.addBindValue(self.champ_statut.currentData())
        if self.exercice_id is not None:
            query.addBindValue(self.exercice_id)

        if not query.exec():
            QMessageBox.critical(
                self, "Erreur", f"Impossible d'enregistrer l'exercice :\n{query.lastError().text()}"
            )
            return

        self.accept()
