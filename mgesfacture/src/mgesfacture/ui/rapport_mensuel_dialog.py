"""Dialogue du rapport mensuel des factures : choix de la période, aperçu à
l'écran (mêmes données que le PDF), export PDF."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtSql import QSqlDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mgesfacture.support.formatage import formater_montant
from mgesfacture.support.rapport_mensuel import (
    charger_rapport_mensuel,
    imprimer_rapport_pdf,
    libelle_periode,
    periodes_disponibles,
)
from mgesfacture.ui.icone import icone_ronde_verte


class RapportMensuelDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowIcon(icone_ronde_verte())
        self.setWindowTitle("Rapport mensuel des factures")
        self.resize(640, 520)

        self.champ_periode = QComboBox(self)
        for annee_mois in periodes_disponibles(db):
            self.champ_periode.addItem(libelle_periode(annee_mois), annee_mois)
        self.champ_periode.currentIndexChanged.connect(self._actualiser_apercu)

        formulaire = QFormLayout()
        formulaire.addRow("Période :", self.champ_periode)

        self.label_total = QLabel(self)

        self.arbre = QTreeWidget(self)
        self.arbre.setHeaderLabels(["Fournisseur / Référence", "N° facture", "Date", "Montant"])
        self.arbre.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        bouton_exporter = QPushButton("Exporter en PDF…", self)
        bouton_exporter.clicked.connect(self._exporter_pdf)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        boutons.accepted.connect(self.accept)
        boutons.addButton(bouton_exporter, QDialogButtonBox.ButtonRole.ActionRole)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(self.arbre)
        layout.addWidget(self.label_total)
        layout.addWidget(boutons)

        if self.champ_periode.count() == 0:
            self.arbre.setEnabled(False)
            self.label_total.setText("Aucune facture enregistrée.")
        else:
            self._actualiser_apercu()

    def _periode_selectionnee(self) -> str | None:
        return self.champ_periode.currentData()

    def _actualiser_apercu(self) -> None:
        annee_mois = self._periode_selectionnee()
        self.arbre.clear()
        if annee_mois is None:
            self.label_total.setText("")
            return

        rapport = charger_rapport_mensuel(self.db, annee_mois)
        for groupe in rapport.groupes:
            item_fournisseur = QTreeWidgetItem(
                [f"{groupe.fournisseur_nom}  ({len(groupe.factures)})", "", "", formater_montant(groupe.sous_total)]
            )
            font = item_fournisseur.font(0)
            font.setBold(True)
            for colonne in range(4):
                item_fournisseur.setFont(colonne, font)
            for facture in groupe.factures:
                QTreeWidgetItem(
                    item_fournisseur,
                    [
                        facture["reference_interne"],
                        facture["numero_facture"],
                        facture["date_facture"],
                        formater_montant(facture["montant"]),
                    ],
                )
            self.arbre.addTopLevelItem(item_fournisseur)
            item_fournisseur.setExpanded(True)

        self.label_total.setText(
            f"<b>Total général ({rapport.nb_factures} facture(s)) : {formater_montant(rapport.total_general)}</b>"
        )

    def _exporter_pdf(self) -> None:
        annee_mois = self._periode_selectionnee()
        if annee_mois is None:
            return

        nom_par_defaut = f"rapport_mensuel_{annee_mois}.pdf"
        chemin_str, _ = QFileDialog.getSaveFileName(self, "Exporter le rapport", nom_par_defaut, "Fichiers PDF (*.pdf)")
        if not chemin_str:
            return

        rapport = charger_rapport_mensuel(self.db, annee_mois)
        try:
            imprimer_rapport_pdf(rapport, Path(chemin_str))
        except OSError as erreur:
            QMessageBox.critical(self, "Erreur", f"Impossible d'écrire le fichier :\n{erreur}")
            return

        QMessageBox.information(self, "Export terminé", f"Rapport enregistré :\n{chemin_str}")
