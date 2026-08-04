"""Dialogue en lecture seule : historique des règlements d'un tiers (facture
par facture ou groupés)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mgescompta.support.formatage import formater_montant
from mgescompta.support.tiers_releve import charger_infos_tiers, reglements_tiers


class TiersReglementsDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None, tiers_id: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Règlements du tiers")
        self.resize(880, 440)

        layout = QVBoxLayout(self)

        infos = charger_infos_tiers(db, tiers_id)
        if infos is None:
            layout.addWidget(QLabel("Ce tiers n'existe plus."))
            boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            boutons.rejected.connect(self.reject)
            layout.addWidget(boutons)
            return

        layout.addWidget(QLabel(f"<b>{infos.numero} — {infos.intitule}</b>"))

        reglements = reglements_tiers(db, tiers_id)

        table = QTableWidget(self)
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            ["Date", "Libellé", "Montant", "Mode", "Banque/opérateur", "N° compte", "Référence"]
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setRowCount(len(reglements))
        total = 0.0
        for row, reglement in enumerate(reglements):
            table.setItem(row, 0, QTableWidgetItem(reglement["date"]))
            table.setItem(row, 1, QTableWidgetItem(reglement["libelle"]))
            table.setItem(row, 2, QTableWidgetItem(formater_montant(reglement["montant"])))
            table.setItem(row, 3, QTableWidgetItem(reglement["mode_paiement_libelle"]))
            table.setItem(row, 4, QTableWidgetItem(reglement["banque_operateur"] or "—"))
            table.setItem(row, 5, QTableWidgetItem(reglement["numero_compte"] or "—"))
            table.setItem(row, 6, QTableWidgetItem(reglement["reference_paiement"] or "—"))
            total += reglement["montant"]
        layout.addWidget(table)

        layout.addWidget(QLabel(f"<b>Total réglé : {formater_montant(total)}</b>"))

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)
