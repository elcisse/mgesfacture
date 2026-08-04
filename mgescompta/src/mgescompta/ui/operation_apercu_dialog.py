"""Dialogue en lecture seule : aperçu complet d'une opération comptable
(en-tête + toutes ses écritures débit/crédit avec les totaux)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mgescompta.support.formatage import formater_montant

STATUT_LABELS: dict[str, str] = {
    "EN_ATTENTE": "En attente",
    "VALIDEE": "Validée",
    "ANNULEE": "Annulée",
}
SENS_LABELS: dict[str, str] = {"DEBIT": "Débit", "CREDIT": "Crédit"}


class OperationApercuDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None, operation_id: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperçu de l'opération comptable")
        self.resize(620, 480)

        layout = QVBoxLayout(self)

        entete = QSqlQuery(db)
        entete.prepare(
            "SELECT o.date, o.libelle, o.piece_reference, o.statut, j.code, j.intitule "
            "FROM operations_comptables o JOIN code_journaux j ON j.id = o.journal_id "
            "WHERE o.id = ?"
        )
        entete.addBindValue(operation_id)
        entete.exec()
        if not entete.next():
            layout.addWidget(QLabel("Cette opération n'existe plus."))
            boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            boutons.rejected.connect(self.reject)
            layout.addWidget(boutons)
            return

        date, libelle, piece_reference, statut, journal_code, journal_intitule = (
            entete.value(0), entete.value(1), entete.value(2), entete.value(3), entete.value(4), entete.value(5)
        )

        formulaire = QFormLayout()
        formulaire.addRow("Journal :", QLabel(f"{journal_code} — {journal_intitule}"))
        formulaire.addRow("Date :", QLabel(date))
        formulaire.addRow("Libellé :", QLabel(libelle))
        formulaire.addRow("Pièce jointe (réf.) :", QLabel(piece_reference or "—"))
        formulaire.addRow("Statut :", QLabel(STATUT_LABELS.get(statut, statut)))
        layout.addLayout(formulaire)

        layout.addWidget(QLabel("<b>Écritures</b>"))

        table = QTableWidget(self)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Compte", "Libellé", "Montant", "Sens"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)

        lignes_query = QSqlQuery(db)
        lignes_query.prepare(
            "SELECT compte, libelle, montant, sens FROM ecritures_comptables "
            "WHERE operation_id = ? ORDER BY id"
        )
        lignes_query.addBindValue(operation_id)
        lignes_query.exec()

        lignes = []
        while lignes_query.next():
            lignes.append(
                (lignes_query.value(0), lignes_query.value(1), lignes_query.value(2), lignes_query.value(3))
            )

        total_debit = 0.0
        total_credit = 0.0
        table.setRowCount(len(lignes))
        for row, (compte, libelle_ligne, montant, sens) in enumerate(lignes):
            table.setItem(row, 0, QTableWidgetItem(compte))
            table.setItem(row, 1, QTableWidgetItem(libelle_ligne))
            table.setItem(row, 2, QTableWidgetItem(formater_montant(montant)))
            table.setItem(row, 3, QTableWidgetItem(SENS_LABELS.get(sens, sens)))
            if sens == "DEBIT":
                total_debit += montant
            else:
                total_credit += montant

        layout.addWidget(table)

        equilibre = "équilibrée ✓" if round(total_debit, 2) == round(total_credit, 2) else "déséquilibrée ⚠"
        layout.addWidget(
            QLabel(
                f"<b>Total débit : {formater_montant(total_debit)}    "
                f"Total crédit : {formater_montant(total_credit)}    ({equilibre})</b>"
            )
        )

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)
