"""Dialogue en lecture seule : aperçu complet d'un tiers (coordonnées,
factures, solde dû)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase
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
from mgescompta.support.tiers_releve import STATUT_LABELS, charger_releve


class TiersApercuDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None, tiers_id: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperçu du tiers")
        self.resize(680, 520)

        layout = QVBoxLayout(self)

        releve = charger_releve(db, tiers_id)
        if releve is None:
            layout.addWidget(QLabel("Ce tiers n'existe plus."))
            boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            boutons.rejected.connect(self.reject)
            layout.addWidget(boutons)
            return

        infos = releve.infos
        localisation = ", ".join(p for p in (infos.localite, infos.departement, infos.region) if p) or "—"

        formulaire = QFormLayout()
        formulaire.addRow("Tiers :", QLabel(f"{infos.numero} — {infos.intitule}"))
        formulaire.addRow("Type :", QLabel(infos.type))
        formulaire.addRow("Compte collectif :", QLabel(infos.compte_collectif))
        formulaire.addRow("Classification :", QLabel(infos.classification or "—"))
        formulaire.addRow("Localisation :", QLabel(localisation))
        formulaire.addRow("Adresse :", QLabel(infos.adresse or "—"))
        formulaire.addRow("Téléphone :", QLabel(infos.telephone or "—"))
        formulaire.addRow("Email :", QLabel(infos.email or "—"))
        formulaire.addRow("Actif :", QLabel("Oui" if infos.actif else "Non"))
        layout.addLayout(formulaire)

        layout.addWidget(QLabel("<b>Factures</b>"))

        table = QTableWidget(self)
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["N° facture", "Date", "Montant", "Réglé", "Solde", "Statut"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setRowCount(len(releve.factures))
        for row, facture in enumerate(releve.factures):
            table.setItem(row, 0, QTableWidgetItem(facture["numero_facture"]))
            table.setItem(row, 1, QTableWidgetItem(facture["date_facture"]))
            table.setItem(row, 2, QTableWidgetItem(formater_montant(facture["montant"])))
            table.setItem(row, 3, QTableWidgetItem(formater_montant(facture["montant_regle"])))
            table.setItem(row, 4, QTableWidgetItem(formater_montant(facture["solde"])))
            table.setItem(row, 5, QTableWidgetItem(STATUT_LABELS.get(facture["statut"], facture["statut"])))
        layout.addWidget(table)

        layout.addWidget(QLabel(f"<b>Solde dû : {formater_montant(releve.solde_du)}</b>"))

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)
