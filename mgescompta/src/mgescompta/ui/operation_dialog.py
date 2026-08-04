"""Dialogue de création/modification d'une opération comptable (en-tête d'une saisie)."""
from __future__ import annotations

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

STATUT_LABELS: dict[str, str] = {
    "EN_ATTENTE": "En attente",
    "VALIDEE": "Validée",
    "ANNULEE": "Annulée",
}


class OperationDialog(QDialog):
    """operation_id=None -> création (validée automatiquement) ; sinon -> modification."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, operation_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.operation_id = operation_id
        self.setWindowTitle("Modifier l'opération comptable" if operation_id else "Nouvelle opération comptable")
        self.resize(420, 260)

        self.champ_journal = QComboBox(self)
        self._charger_journaux()

        self.champ_date = QDateEdit(QDate.currentDate(), self)
        self.champ_date.setCalendarPopup(True)
        self.champ_date.setDisplayFormat("dd/MM/yyyy")

        self.champ_libelle = QLineEdit(self)
        self.champ_piece = QLineEdit(self)

        self.champ_statut = QComboBox(self)
        for valeur, libelle in STATUT_LABELS.items():
            self.champ_statut.addItem(libelle, valeur)
        if operation_id is None:
            self.champ_statut.setCurrentIndex(self.champ_statut.findData("VALIDEE"))

        formulaire = QFormLayout()
        formulaire.addRow("Journal :", self.champ_journal)
        formulaire.addRow("Date :", self.champ_date)
        formulaire.addRow("Libellé :", self.champ_libelle)
        formulaire.addRow("Pièce jointe (réf.) :", self.champ_piece)
        formulaire.addRow("Statut :", self.champ_statut)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if operation_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if operation_id is not None:
            self._charger(operation_id)

    def _charger_journaux(self) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT id, code, intitule FROM code_journaux ORDER BY code")
        while query.next():
            self.champ_journal.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _charger(self, operation_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT journal_id, date, libelle, piece_reference, statut FROM operations_comptables WHERE id = ?"
        )
        query.addBindValue(operation_id)
        query.exec()
        if not query.next():
            return
        index_journal = self.champ_journal.findData(query.value(0))
        if index_journal >= 0:
            self.champ_journal.setCurrentIndex(index_journal)
        self.champ_date.setDate(QDate.fromString(query.value(1), "yyyy-MM-dd"))
        self.champ_libelle.setText(query.value(2))
        self.champ_piece.setText(query.value(3) or "")
        self.champ_statut.setCurrentIndex(self.champ_statut.findData(query.value(4)))

    def _valider(self) -> None:
        if self.champ_journal.count() == 0:
            QMessageBox.warning(self, "Aucun journal", "Créez d'abord un journal comptable.")
            return

        libelle = self.champ_libelle.text().strip()
        if not libelle:
            QMessageBox.warning(self, "Champ manquant", "Le libellé est obligatoire.")
            return

        query = QSqlQuery(self.db)
        if self.operation_id is None:
            query.prepare(
                "INSERT INTO operations_comptables (journal_id, date, libelle, piece_reference, statut) "
                "VALUES (?, ?, ?, ?, ?)"
            )
        else:
            query.prepare(
                "UPDATE operations_comptables SET journal_id = ?, date = ?, libelle = ?, "
                "piece_reference = ?, statut = ? WHERE id = ?"
            )
        query.addBindValue(self.champ_journal.currentData())
        query.addBindValue(self.champ_date.date().toString("yyyy-MM-dd"))
        query.addBindValue(libelle)
        query.addBindValue(self.champ_piece.text().strip() or None)
        query.addBindValue(self.champ_statut.currentData())
        if self.operation_id is not None:
            query.addBindValue(self.operation_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer l'opération :\n{query.lastError().text()}")
            return

        self.accept()
