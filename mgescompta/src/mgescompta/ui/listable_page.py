"""Page composite générique : liste (SqlTablePage) + bouton ouvrant un
dialogue de création, avec rafraîchissement automatique après validation.
Peut aussi proposer Modifier/Supprimer, avec des garde-fous optionnels
(ex. n'autoriser que les lignes au statut « En attente »)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from mgescompta.ui.table_page import SqlTablePage

DialogFactory = Callable[[QSqlDatabase, QWidget], "QDialog | None"]
EditDialogFactory = Callable[[QSqlDatabase, QWidget, int], "QDialog | None"]
Garde = Callable[[QSqlDatabase, int], "str | None"]  # renvoie un message d'erreur si bloqué, sinon None


class ListablePage(QWidget):
    def __init__(
        self,
        db: QSqlDatabase,
        table: str,
        titre: str,
        colonnes: dict[str, str],
        dialog_factory: DialogFactory,
        bouton_texte: str = "Ajouter…",
        edit_dialog_factory: EditDialogFactory | None = None,
        permettre_suppression: bool = False,
        garde_modification: Garde | None = None,
        garde_suppression: Garde | None = None,
        relations: dict[str, tuple[str, str]] | None = None,
        tri: str | None = None,
        colonnes_montant: set[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """dialog_factory(db, parent) -> QDialog | None : construit le
        dialogue de création. edit_dialog_factory(db, parent, id) -> QDialog | None :
        construit le dialogue de modification pour la ligne sélectionnée.
        Les deux peuvent retourner None (après avoir averti l'utilisateur) si
        un préalable manque. garde_modification/garde_suppression(db, id) ->
        message d'erreur ou None : bloque l'action avec ce message si non-None
        (ex. « seules les lignes en attente peuvent être modifiées »)."""
        super().__init__(parent)
        self.db = db
        self.table = table
        self._dialog_factory = dialog_factory
        self._edit_dialog_factory = edit_dialog_factory
        self._garde_modification = garde_modification
        self._garde_suppression = garde_suppression

        self.liste = SqlTablePage(
            db, table, titre, colonnes, self, relations=relations, tri=tri, colonnes_montant=colonnes_montant
        )
        self.liste.layout().itemAt(0).widget().hide()  # masque le <h2> dupliqué, le titre est dans l'en-tête ci-dessous

        bouton_ajouter = QPushButton(bouton_texte, self)
        bouton_ajouter.clicked.connect(self._ouvrir_creation)

        self.entete_layout = QHBoxLayout()
        self.entete_layout.addWidget(QLabel(f"<h2>{titre}</h2>"))
        self.entete_layout.addStretch(1)
        self.entete_layout.addWidget(bouton_ajouter)

        if edit_dialog_factory is not None:
            bouton_modifier = QPushButton("Modifier la sélection", self)
            bouton_modifier.clicked.connect(self._ouvrir_modification)
            self.entete_layout.addWidget(bouton_modifier)

        if permettre_suppression:
            bouton_supprimer = QPushButton("Supprimer la sélection", self)
            bouton_supprimer.clicked.connect(self._supprimer_selection)
            self.entete_layout.addWidget(bouton_supprimer)

        layout = QVBoxLayout(self)
        layout.addLayout(self.entete_layout)
        layout.addWidget(self.liste)

    def _ouvrir_creation(self) -> None:
        dialog = self._dialog_factory(self.db, self)
        if dialog is None:
            return
        if dialog.exec():
            self.liste.refresh()

    def _selection_id(self) -> int | None:
        lignes = self.liste.view.selectionModel().selectedRows()
        if not lignes:
            QMessageBox.information(self, "Aucune sélection", "Sélectionnez une ligne.")
            return None
        colonne_id = self.liste.model.fieldIndex("id")
        return self.liste.model.data(self.liste.model.index(lignes[0].row(), colonne_id))

    def _ouvrir_modification(self) -> None:
        row_id = self._selection_id()
        if row_id is None:
            return
        if self._garde_modification is not None:
            erreur = self._garde_modification(self.db, row_id)
            if erreur:
                QMessageBox.warning(self, "Modification impossible", erreur)
                return

        dialog = self._edit_dialog_factory(self.db, self, row_id)
        if dialog is None:
            return
        if dialog.exec():
            self.liste.refresh()

    def _supprimer_selection(self) -> None:
        row_id = self._selection_id()
        if row_id is None:
            return
        if self._garde_suppression is not None:
            erreur = self._garde_suppression(self.db, row_id)
            if erreur:
                QMessageBox.warning(self, "Suppression impossible", erreur)
                return

        reponse = QMessageBox.question(
            self,
            "Supprimer",
            "Voulez-vous vraiment supprimer cette ligne ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reponse != QMessageBox.StandardButton.Yes:
            return

        query = QSqlQuery(self.db)
        query.prepare(f"DELETE FROM {self.table} WHERE id = ?")
        query.addBindValue(row_id)
        if not query.exec():
            QMessageBox.warning(
                self,
                "Suppression impossible",
                "Cette ligne est probablement utilisée ailleurs dans l'application.\n"
                "Retirez-en les usages avant de la supprimer.",
            )
            return

        self.liste.refresh()

    def refresh(self) -> None:
        self.liste.refresh()
