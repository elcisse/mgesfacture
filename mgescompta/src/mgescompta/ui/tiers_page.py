"""Page Tiers : liste + création/modification/suppression, avec recherche
par numéro ou intitulé et menu contextuel (clic droit)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QWidget

from mgescompta.support.factures import factures_a_regler
from mgescompta.support.tiers_releve import charger_releve, imprimer_releve_pdf
from mgescompta.ui.facture_reglement_groupe_dialog import FactureReglementGroupeDialog
from mgescompta.ui.listable_page import ListablePage
from mgescompta.ui.tiers_apercu_dialog import TiersApercuDialog
from mgescompta.ui.tiers_dialog import TiersDialog
from mgescompta.ui.tiers_reglements_dialog import TiersReglementsDialog

COLONNES = {
    "id": "ID",
    "numero": "Numéro",
    "intitule": "Intitulé",
    "type": "Type",
    "compte_collectif": "Compte collectif",
    "classification_id": "Classification",
    "region_id": "Région",
    "departement_id": "Département",
    "localite_id": "Localité",
    "actif": "Actif",
}


class TiersPage(ListablePage):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(
            db, "plan_tiers", "Tiers", COLONNES,
            TiersDialog, "Nouveau tiers…",
            edit_dialog_factory=TiersDialog,
            permettre_suppression=True,
            relations={
                "classification_id": ("classification", "libelle"),
                "region_id": ("region", "nom"),
                "departement_id": ("departement", "nom"),
                "localite_id": ("localite", "nom"),
            },
            parent=parent,
        )

        self.champ_recherche = QLineEdit(self)
        self.champ_recherche.setPlaceholderText("Rechercher par numéro ou intitulé…")
        self.champ_recherche.textChanged.connect(self._filtrer)

        barre_recherche = QHBoxLayout()
        barre_recherche.addWidget(QLabel("Recherche :"))
        barre_recherche.addWidget(self.champ_recherche)
        self.layout().insertLayout(1, barre_recherche)

        self.liste.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.liste.view.customContextMenuRequested.connect(self._menu_contextuel)

    def _filtrer(self, texte: str) -> None:
        texte = texte.strip()
        if not texte:
            self.liste.model.setFilter("")
        else:
            echappe = texte.replace("'", "''")
            self.liste.model.setFilter(f"numero LIKE '%{echappe}%' OR intitule LIKE '%{echappe}%'")
        self.liste.model.select()

    def _menu_contextuel(self, position) -> None:
        index = self.liste.view.indexAt(position)
        if not index.isValid():
            return
        self.liste.view.selectRow(index.row())

        menu = QMenu(self)
        menu.addAction("Aperçu du tiers…", self._apercu_selection)
        menu.addAction("Voir les factures", self._voir_factures_selection)
        menu.addAction("Voir les règlements", self._voir_reglements_selection)
        menu.addAction("Imprimer le relevé (PDF)…", self._imprimer_releve_selection)
        menu.addSeparator()
        menu.addAction("Modifier la sélection", self._ouvrir_modification)
        menu.addAction("Régler…", self._regler_selection)
        menu.addSeparator()
        menu.addAction("Supprimer la sélection", self._supprimer_selection)
        menu.exec(self.liste.view.viewport().mapToGlobal(position))

    def _apercu_selection(self) -> None:
        tiers_id = self._selection_id()
        if tiers_id is None:
            return
        TiersApercuDialog(self.db, self, tiers_id).exec()

    def _voir_factures_selection(self) -> None:
        tiers_id = self._selection_id()
        if tiers_id is None:
            return
        query = QSqlQuery(self.db)
        query.prepare("SELECT numero FROM plan_tiers WHERE id = ?")
        query.addBindValue(tiers_id)
        query.exec()
        if not query.next():
            return
        numero = query.value(0)

        fenetre = self.window()
        if not hasattr(fenetre, "ouvrir_module"):
            return
        fenetre.ouvrir_module("factures")
        page_factures = fenetre._sous_fenetres["factures"].widget()
        page_factures.champ_recherche.setText(numero)

    def _voir_reglements_selection(self) -> None:
        tiers_id = self._selection_id()
        if tiers_id is None:
            return
        TiersReglementsDialog(self.db, self, tiers_id).exec()

    def _imprimer_releve_selection(self) -> None:
        tiers_id = self._selection_id()
        if tiers_id is None:
            return
        releve = charger_releve(self.db, tiers_id)
        if releve is None:
            return

        nom_defaut = f"releve_{releve.infos.numero}.pdf"
        chemin_str, _ = QFileDialog.getSaveFileName(
            self, "Imprimer le relevé du tiers", nom_defaut, "Fichiers PDF (*.pdf)"
        )
        if not chemin_str:
            return

        try:
            imprimer_releve_pdf(releve, Path(chemin_str))
        except OSError as erreur:
            QMessageBox.critical(self, "Erreur", f"Impossible d'écrire le fichier :\n{erreur}")
            return

        QMessageBox.information(self, "Relevé imprimé", f"Relevé enregistré :\n{chemin_str}")

    def _regler_selection(self) -> None:
        tiers_id = self._selection_id()
        if tiers_id is None:
            return
        if not factures_a_regler(self.db, tiers_id):
            QMessageBox.information(
                self, "Rien à régler", "Ce tiers n'a aucune facture comptabilisée à régler."
            )
            return
        if FactureReglementGroupeDialog(self.db, self, tiers_id).exec():
            QMessageBox.information(self, "Réglé", "Le règlement a été enregistré.")
