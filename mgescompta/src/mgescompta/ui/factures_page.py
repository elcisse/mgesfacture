"""Page Factures fournisseurs : liste + création/modification/suppression
(tant que non comptabilisée), puis comptabilisation et règlements (total ou
partiels), sans jamais repasser par la saisie manuelle d'écritures."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

from mgescompta.support.factures import FactureInvalideError, comptabiliser_facture, garde_facture_comptabilisee
from mgescompta.support.import_factures import importer_csv
from mgescompta.ui.facture_apercu_dialog import FactureApercuDialog
from mgescompta.ui.facture_dialog import FactureDialog
from mgescompta.ui.facture_reglement_dialog import FactureReglementDialog
from mgescompta.ui.listable_page import ListablePage

COLONNES = {
    "id": "ID",
    "reference_interne": "Référence",
    "tiers_id": "Fournisseur",
    "numero_facture": "N° facture",
    "date_facture": "Date",
    "annee_mois": "Année-mois",
    "date_echeance": "Échéance",
    "montant": "Montant",
    "montant_regle": "Réglé",
    "statut": "Statut",
}


class FacturesPage(ListablePage):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(
            db, "factures", "Factures", COLONNES,
            FactureDialog, "Nouvelle facture…",
            edit_dialog_factory=FactureDialog,
            permettre_suppression=True,
            garde_modification=garde_facture_comptabilisee,
            garde_suppression=garde_facture_comptabilisee,
            relations={"tiers_id": ("plan_tiers", "intitule")},
            colonnes_montant={"montant", "montant_regle"},
            parent=parent,
        )

        bouton_importer = QPushButton("Importer…", self)
        bouton_importer.clicked.connect(self._importer)
        self.entete_layout.addWidget(bouton_importer)

        bouton_comptabiliser = QPushButton("Comptabiliser", self)
        bouton_comptabiliser.clicked.connect(self._comptabiliser_selection)
        self.entete_layout.addWidget(bouton_comptabiliser)

        bouton_regler = QPushButton("Régler…", self)
        bouton_regler.clicked.connect(self._regler_selection)
        self.entete_layout.addWidget(bouton_regler)

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
        menu.addAction("Comptabiliser", self._comptabiliser_selection)
        menu.addAction("Régler…", self._regler_selection)
        menu.addSeparator()
        menu.addAction("Supprimer la sélection", self._supprimer_selection)
        menu.exec(self.liste.view.viewport().mapToGlobal(position))

    def _apercu_selection(self) -> None:
        facture_id = self._selection_id()
        if facture_id is None:
            return
        FactureApercuDialog(self.db, self, facture_id).exec()

    def _importer(self) -> None:
        chemin_str, _ = QFileDialog.getOpenFileName(self, "Importer des factures", "", "Fichiers CSV (*.csv)")
        if not chemin_str:
            return

        try:
            resultat = importer_csv(self.db, Path(chemin_str))
        except (OSError, ValueError) as erreur:
            QMessageBox.critical(self, "Erreur", f"Impossible d'importer le fichier :\n{erreur}")
            return

        self.liste.refresh()

        resume = (
            f"{resultat.nb_importees} facture(s) importée(s).\n"
            f"{resultat.nb_deja_importees} déjà importée(s) (ignorée(s)).\n"
            f"{len(resultat.erreurs)} erreur(s).\n"
            f"{len(resultat.modifiees)} déjà importée(s) mais modifiée(s) depuis (à vérifier manuellement)."
        )
        if resultat.erreurs or resultat.modifiees:
            details = []
            if resultat.erreurs:
                details.append("=== Erreurs ===")
                details.extend(
                    f"Ligne {e.numero_ligne} (id_source {e.id_source}) : {e.message}" for e in resultat.erreurs
                )
            if resultat.modifiees:
                details.append("=== Modifiées depuis leur import (non resynchronisées) ===")
                details.extend(
                    f"Ligne {m.numero_ligne} (id_source {m.id_source}) : {m.message}" for m in resultat.modifiees
                )

            boite = QMessageBox(self)
            boite.setIcon(QMessageBox.Icon.Warning)
            boite.setWindowTitle("Import terminé avec des points à vérifier")
            boite.setText(resume)
            boite.setDetailedText("\n".join(details))
            boite.exec()
        else:
            QMessageBox.information(self, "Import terminé", resume)

    def _filtrer(self, texte: str) -> None:
        texte = texte.strip()
        if not texte:
            self.liste.model.setFilter("")
        else:
            echappe = texte.replace("'", "''")
            self.liste.model.setFilter(
                f"numero_facture LIKE '%{echappe}%' OR "
                f"tiers_id IN (SELECT id FROM plan_tiers WHERE intitule LIKE '%{echappe}%' OR numero LIKE '%{echappe}%')"
            )
        self.liste.model.select()

    def _comptabiliser_selection(self) -> None:
        facture_id = self._selection_id()
        if facture_id is None:
            return
        try:
            resultat = comptabiliser_facture(self.db, facture_id)
        except FactureInvalideError as erreur:
            QMessageBox.warning(self, "Comptabilisation impossible", str(erreur))
            return

        self.liste.refresh()
        QMessageBox.information(self, "Facture comptabilisée", f"Opération créée : {resultat.libelle}")

    def _regler_selection(self) -> None:
        facture_id = self._selection_id()
        if facture_id is None:
            return

        query = QSqlQuery(self.db)
        query.prepare("SELECT operation_constat_id, statut FROM factures WHERE id = ?")
        query.addBindValue(facture_id)
        query.exec()
        query.next()
        operation_constat_id, statut = query.value(0), query.value(1)

        if not operation_constat_id:
            # NB: QSqlQuery.value() renvoie '' (pas None) pour un NULL entier.
            QMessageBox.warning(self, "Règlement impossible", "Comptabilisez d'abord la facture avant de la régler.")
            return
        if statut == "SOLDEE":
            QMessageBox.information(self, "Déjà soldée", "Cette facture est déjà entièrement réglée.")
            return

        dialog = FactureReglementDialog(self.db, self, facture_id)
        if dialog.exec():
            self.liste.refresh()
            QMessageBox.information(self, "Réglé", "Le règlement a été enregistré.")
