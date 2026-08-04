"""Dialogue Paramètres : seul endroit où le compte collectif de chaque type
de tiers, et le compte de charge de chaque catégorie de fournisseur, peuvent
être fixés/modifiés -- jamais ligne par ligne dans les dialogues Tiers ou
Facture, pour garantir une valeur identique pour tous les tiers/factures
concernés."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from mgesfacture.ui.icone import icone_ronde_verte

TYPES_TIERS = ["FOURNISSEUR", "ADHERENT", "SALARIE", "AUTRE"]
LABELS_TYPES: dict[str, str] = {
    "FOURNISSEUR": "Fournisseur",
    "ADHERENT": "Adhérent",
    "SALARIE": "Salarié",
    "AUTRE": "Autre",
}

CATEGORIES_CHARGE = ["SANTE", "FONCTIONNEMENT"]
LABELS_CATEGORIES_CHARGE: dict[str, str] = {
    "SANTE": "Santé (hôpitaux, pharmacies…)",
    "FONCTIONNEMENT": "Biens et services de fonctionnement",
}


class ParametresDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowIcon(icone_ronde_verte())
        self.db = db
        self.setWindowTitle("Paramètres")
        self.resize(420, 320)

        self.champs_collectif: dict[str, QLineEdit] = {}
        self.champs_charge: dict[str, QLineEdit] = {}

        formulaire = QFormLayout()
        formulaire.addRow(QLabel("<b>Comptes collectifs par type de tiers</b>"))
        for type_ in TYPES_TIERS:
            champ = QLineEdit(self)
            self.champs_collectif[type_] = champ
            formulaire.addRow(f"Compte collectif {LABELS_TYPES[type_]} :", champ)

        formulaire.addRow(QLabel("<b>Comptes de charge par catégorie de fournisseur</b>"))
        for categorie in CATEGORIES_CHARGE:
            champ = QLineEdit(self)
            self.champs_charge[categorie] = champ
            formulaire.addRow(f"Compte de charge {LABELS_CATEGORIES_CHARGE[categorie]} :", champ)

        self._charger()

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        bouton_valider = boutons.addButton("Enregistrer", QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

    def _charger(self) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT type, compte_collectif FROM parametres_comptes_collectifs")
        while query.next():
            type_, valeur = query.value(0), query.value(1)
            if type_ in self.champs_collectif:
                self.champs_collectif[type_].setText(valeur or "")

        query_charge = QSqlQuery(self.db)
        query_charge.exec("SELECT categorie, compte_charge FROM parametres_comptes_charge")
        while query_charge.next():
            categorie, valeur = query_charge.value(0), query_charge.value(1)
            if categorie in self.champs_charge:
                self.champs_charge[categorie].setText(valeur or "")

    def _valider(self) -> None:
        valeurs_collectif = {type_: champ.text().strip() for type_, champ in self.champs_collectif.items()}
        valeurs_charge = {categorie: champ.text().strip() for categorie, champ in self.champs_charge.items()}

        for type_, valeur in valeurs_collectif.items():
            update = QSqlQuery(self.db)
            update.prepare("UPDATE parametres_comptes_collectifs SET compte_collectif = ? WHERE type = ?")
            update.addBindValue(valeur)
            update.addBindValue(type_)
            if not update.exec():
                QMessageBox.critical(
                    self, "Erreur", f"Impossible d'enregistrer les paramètres :\n{update.lastError().text()}"
                )
                return

            # Le compte collectif d'un tiers n'est modifiable que par ce
            # biais : on répercute donc le changement sur tous les tiers du
            # type concerné (source unique de vérité, pas de divergence
            # possible entre tiers d'un même type).
            propagation = QSqlQuery(self.db)
            propagation.prepare("UPDATE tiers SET compte_collectif = ? WHERE type = ?")
            propagation.addBindValue(valeur)
            propagation.addBindValue(type_)
            propagation.exec()

        for categorie, valeur in valeurs_charge.items():
            update_charge = QSqlQuery(self.db)
            update_charge.prepare("UPDATE parametres_comptes_charge SET compte_charge = ? WHERE categorie = ?")
            update_charge.addBindValue(valeur)
            update_charge.addBindValue(categorie)
            if not update_charge.exec():
                QMessageBox.critical(
                    self, "Erreur", f"Impossible d'enregistrer les paramètres :\n{update_charge.lastError().text()}"
                )
                return
            # Pas de propagation ici : le compte de charge n'est pas stocké
            # sur le tiers (contrairement au compte collectif), il n'est
            # résolu qu'au moment de l'export (voir support/comptes_charge.py).

        self.accept()
