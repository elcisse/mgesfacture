"""Dialogue en lecture seule : aperçu complet d'une facture fournisseur
(en-tête + l'historique des opérations comptables liées : constatation et
règlements successifs)."""
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
    "IMPAYEE": "Impayée",
    "PARTIELLEMENT_REGLEE": "Partiellement réglée",
    "SOLDEE": "Soldée",
}


class FactureApercuDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None, facture_id: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperçu de la facture")
        self.resize(620, 480)

        layout = QVBoxLayout(self)

        entete = QSqlQuery(db)
        entete.prepare(
            "SELECT f.numero_facture, f.date_facture, f.annee_mois, f.date_echeance, f.compte_charge, f.libelle, "
            "f.montant, f.montant_regle, f.statut, f.operation_constat_id, t.intitule, t.compte_collectif, "
            "f.reference_interne "
            "FROM factures f JOIN plan_tiers t ON t.id = f.tiers_id WHERE f.id = ?"
        )
        entete.addBindValue(facture_id)
        entete.exec()
        if not entete.next():
            layout.addWidget(QLabel("Cette facture n'existe plus."))
            boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            boutons.rejected.connect(self.reject)
            layout.addWidget(boutons)
            return

        (numero, date_facture, annee_mois, date_echeance, compte_charge, libelle, montant, montant_regle,
         statut, operation_constat_id, fournisseur, compte_collectif,
         reference_interne) = (entete.value(i) for i in range(13))

        solde = round(montant - montant_regle, 2)

        formulaire = QFormLayout()
        formulaire.addRow("Fournisseur :", QLabel(fournisseur))
        formulaire.addRow("Référence interne :", QLabel(reference_interne or "—"))
        formulaire.addRow("N° de facture :", QLabel(numero))
        formulaire.addRow("Date de la facture :", QLabel(date_facture))
        formulaire.addRow("Année-mois :", QLabel(annee_mois))
        formulaire.addRow("Échéance :", QLabel(date_echeance or "—"))
        formulaire.addRow("Compte de charge :", QLabel(compte_charge))
        formulaire.addRow("Libellé :", QLabel(libelle or "—"))
        formulaire.addRow("Montant :", QLabel(formater_montant(montant)))
        formulaire.addRow("Montant réglé :", QLabel(formater_montant(montant_regle)))
        formulaire.addRow("Solde restant dû :", QLabel(formater_montant(solde)))
        formulaire.addRow("Statut :", QLabel(STATUT_LABELS.get(statut, statut)))
        layout.addLayout(formulaire)

        layout.addWidget(QLabel("<b>Opérations comptables liées</b>"))

        table = QTableWidget(self)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Date", "Libellé", "Montant"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)

        lignes = []
        if operation_constat_id:
            # NB: QSqlQuery.value() renvoie '' (pas None) pour un NULL entier.
            constat = QSqlQuery(db)
            constat.prepare(
                "SELECT date, libelle, piece_reference FROM operations_comptables WHERE id = ?"
            )
            constat.addBindValue(operation_constat_id)
            constat.exec()
            if constat.next():
                lignes.append((constat.value(0), f"Constatation — {constat.value(1)}", montant))

            reglements = QSqlQuery(db)
            reglements.prepare(
                "SELECT o.date, o.libelle, e.montant FROM operations_comptables o "
                "JOIN ecritures_comptables e ON e.operation_id = o.id "
                "WHERE o.piece_reference = ? AND o.id != ? AND e.sens = 'DEBIT' AND e.compte = ? "
                "ORDER BY o.date, o.id"
            )
            reglements.addBindValue(numero)
            reglements.addBindValue(operation_constat_id)
            reglements.addBindValue(compte_collectif)
            reglements.exec()
            while reglements.next():
                lignes.append((reglements.value(0), reglements.value(1), reglements.value(2)))

        table.setRowCount(len(lignes))
        for row, (date, libelle_ligne, montant_ligne) in enumerate(lignes):
            table.setItem(row, 0, QTableWidgetItem(date))
            table.setItem(row, 1, QTableWidgetItem(libelle_ligne))
            table.setItem(row, 2, QTableWidgetItem(formater_montant(montant_ligne)))

        layout.addWidget(table)

        if not operation_constat_id:
            layout.addWidget(QLabel("Cette facture n'a pas encore été comptabilisée."))

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)
