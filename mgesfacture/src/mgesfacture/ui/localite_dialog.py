"""Dialogue de création d'une localité : sélecteurs région puis département
(cascade), pour l'attacher explicitement au bon département plutôt que de
dépendre implicitement du département déjà sélectionné ailleurs."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from mgesfacture.ui.icone import icone_ronde_verte


class LocaliteDialog(QDialog):
    """Après exec() réussi, .localite_id/.departement_id/.region_id portent
    la localité créée -- pratique pour que l'appelant resynchronise ses
    propres combos (ils peuvent différer de ceux passés en pré-sélection)."""

    def __init__(
        self,
        db: QSqlDatabase,
        parent: QWidget | None = None,
        region_id: int | None = None,
        departement_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowIcon(icone_ronde_verte())
        self.db = db
        self.setWindowTitle("Nouvelle localité")
        self.resize(360, 180)

        self.localite_id: int | None = None
        self.region_id: int | None = None
        self.departement_id: int | None = None

        self.champ_region = QComboBox(self)
        self._charger_regions()

        self.champ_departement = QComboBox(self)
        self.champ_region.currentIndexChanged.connect(self._recharger_departements)
        self._recharger_departements()

        self.champ_nom = QLineEdit(self)

        formulaire = QFormLayout()
        formulaire.addRow("Région :", self.champ_region)
        formulaire.addRow("Département :", self.champ_departement)
        formulaire.addRow("Nom de la localité :", self.champ_nom)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        bouton_valider = boutons.addButton("Créer", QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if region_id is not None:
            index_region = self.champ_region.findData(region_id)
            if index_region >= 0:
                self.champ_region.setCurrentIndex(index_region)  # déclenche _recharger_departements
        if departement_id is not None:
            index_departement = self.champ_departement.findData(departement_id)
            if index_departement >= 0:
                self.champ_departement.setCurrentIndex(index_departement)

    def _charger_regions(self) -> None:
        self.champ_region.addItem("— Aucune —", None)
        query = QSqlQuery(self.db)
        query.exec("SELECT id, code, nom FROM region ORDER BY code")
        while query.next():
            self.champ_region.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _recharger_departements(self) -> None:
        self.champ_departement.clear()
        self.champ_departement.addItem("— Aucun —", None)
        region_id = self.champ_region.currentData()
        if region_id is not None:
            query = QSqlQuery(self.db)
            query.prepare("SELECT id, code, nom FROM departement WHERE region_id = ? ORDER BY code")
            query.addBindValue(region_id)
            query.exec()
            while query.next():
                self.champ_departement.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _valider(self) -> None:
        departement_id = self.champ_departement.currentData()
        if departement_id is None:
            QMessageBox.warning(self, "Champ manquant", "Sélectionnez un département.")
            return
        nom = self.champ_nom.text().strip()
        if not nom:
            QMessageBox.warning(self, "Champ manquant", "Le nom de la localité est obligatoire.")
            return

        query = QSqlQuery(self.db)
        query.prepare("INSERT INTO localite (departement_id, nom) VALUES (?, ?)")
        query.addBindValue(departement_id)
        query.addBindValue(nom)
        if not query.exec():
            QMessageBox.critical(
                self, "Erreur", f"Impossible de créer la localité :\n{query.lastError().text()}"
            )
            return

        self.localite_id = query.lastInsertId()
        self.departement_id = departement_id
        self.region_id = self.champ_region.currentData()
        self.accept()
