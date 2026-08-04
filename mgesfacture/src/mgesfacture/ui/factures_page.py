"""Page Factures : liste + création/modification/suppression, recherche et
menu contextuel (clic droit) avec aperçu. Aucune comptabilisation ni
règlement -- simple registre de factures."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlDatabase
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QWidget

from mgesfacture.support.export_factures import exporter_vers_csv
from mgesfacture.ui.facture_apercu_dialog import FactureApercuDialog
from mgesfacture.ui.facture_dialog import FactureDialog
from mgesfacture.ui.listable_page import ListablePage
from mgesfacture.ui.rapport_mensuel_dialog import RapportMensuelDialog

COLONNES = {
    "id": "ID",
    "reference_interne": "Référence",
    "tiers_id": "Fournisseur",
    "numero_facture": "N° facture",
    "date_facture": "Date",
    "annee_mois": "Année-mois",
    "date_echeance": "Échéance",
    "montant": "Montant",
    "libelle": "Libellé",
    "exportee_le": "Exportée le",
}


class FacturesPage(ListablePage):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(
            db, "factures", "Factures", COLONNES,
            FactureDialog, "Nouvelle facture…",
            edit_dialog_factory=FactureDialog,
            permettre_suppression=True,
            relations={"tiers_id": ("tiers", "intitule")},
            tri="date_facture",
            colonnes_montant={"montant"},
            parent=parent,
        )

        bouton_exporter = QPushButton("Exporter…", self)
        bouton_exporter.clicked.connect(self._exporter)
        self.entete_layout.addWidget(bouton_exporter)

        bouton_rapport = QPushButton("Rapport mensuel…", self)
        bouton_rapport.clicked.connect(self._ouvrir_rapport_mensuel)
        self.entete_layout.addWidget(bouton_rapport)

        self.champ_recherche = QLineEdit(self)
        self.champ_recherche.setPlaceholderText("Rechercher par n° de facture ou nom du fournisseur…")
        self.champ_recherche.textChanged.connect(self._filtrer)

        barre_recherche = QHBoxLayout()
        barre_recherche.addWidget(QLabel("Recherche :"))
        barre_recherche.addWidget(self.champ_recherche)
        self.layout().insertLayout(1, barre_recherche)

        self.liste.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.liste.view.customContextMenuRequested.connect(self._menu_contextuel)

    def _menu_contextuel(self, position) -> None:
        index = self.liste.view.indexAt(position)
        if not index.isValid():
            return
        self.liste.view.selectRow(index.row())

        menu = QMenu(self)
        menu.addAction("Aperçu…", self._apercu_selection)
        menu.addSeparator()
        menu.addAction("Modifier la sélection", self._ouvrir_modification)
        menu.addAction("Supprimer la sélection", self._supprimer_selection)
        menu.exec(self.liste.view.viewport().mapToGlobal(position))

    def _apercu_selection(self) -> None:
        facture_id = self._selection_id()
        if facture_id is None:
            return
        FactureApercuDialog(self.db, self, facture_id).exec()

    def _exporter(self) -> None:
        nom_par_defaut = f"factures_export_{date.today().isoformat()}.csv"
        chemin_str, _ = QFileDialog.getSaveFileName(
            self, "Exporter les factures", nom_par_defaut, "Fichiers CSV (*.csv)"
        )
        if not chemin_str:
            return

        try:
            resultat = exporter_vers_csv(self.db, Path(chemin_str))
        except OSError as erreur:
            QMessageBox.critical(self, "Erreur", f"Impossible d'écrire le fichier :\n{erreur}")
            return
        except RuntimeError as erreur:
            QMessageBox.critical(self, "Erreur", str(erreur))
            return

        self.liste.refresh()
        if resultat.nb_factures == 0:
            QMessageBox.information(self, "Rien à exporter", "Toutes les factures ont déjà été exportées.")
        else:
            QMessageBox.information(
                self, "Export terminé", f"{resultat.nb_factures} facture(s) exportée(s) vers :\n{resultat.chemin}"
            )

    def _ouvrir_rapport_mensuel(self) -> None:
        RapportMensuelDialog(self.db, self).exec()

    def _filtrer(self, texte: str) -> None:
        texte = texte.strip()
        if not texte:
            self.liste.model.setFilter("")
        else:
            echappe = texte.replace("'", "''")
            self.liste.model.setFilter(
                f"numero_facture LIKE '%{echappe}%' OR "
                f"tiers_id IN (SELECT id FROM tiers WHERE intitule LIKE '%{echappe}%' OR numero LIKE '%{echappe}%')"
            )
        self.liste.model.select()
