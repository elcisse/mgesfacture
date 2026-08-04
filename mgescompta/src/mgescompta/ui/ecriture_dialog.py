"""Dialogue de création/modification d'une écriture comptable (ligne débit/crédit d'une opération)."""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

SENS_LABELS: dict[str, str] = {"DEBIT": "Débit", "CREDIT": "Crédit"}
STATUT_LABELS: dict[str, str] = {
    "EN_ATTENTE": "En attente",
    "VALIDEE": "Validée",
    "ANNULEE": "Annulée",
}


class EcritureDialog(QDialog):
    """ecriture_id=None -> création (validée automatiquement) ; sinon -> modification."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, ecriture_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.ecriture_id = ecriture_id
        self.setWindowTitle("Modifier l'écriture comptable" if ecriture_id else "Nouvelle écriture comptable")
        self.resize(420, 340)

        self.champ_operation = QComboBox(self)
        self._charger_operations()
        self.champ_operation.currentIndexChanged.connect(self._prefiltrer_depuis_operation)

        self.champ_date = QDateEdit(QDate.currentDate(), self)
        self.champ_date.setCalendarPopup(True)
        self.champ_date.setDisplayFormat("dd/MM/yyyy")

        self.champ_libelle = QLineEdit(self)

        self.champ_compte = QComboBox(self)
        self._charger_comptes()

        self.champ_montant = QDoubleSpinBox(self)
        self.champ_montant.setRange(1, 999_999_999)
        self.champ_montant.setDecimals(0)
        self.champ_montant.setSuffix(" FCFA")

        self.champ_sens = QComboBox(self)
        for valeur, libelle in SENS_LABELS.items():
            self.champ_sens.addItem(libelle, valeur)

        self.champ_statut = QComboBox(self)
        for valeur, libelle in STATUT_LABELS.items():
            self.champ_statut.addItem(libelle, valeur)
        if ecriture_id is None:
            self.champ_statut.setCurrentIndex(self.champ_statut.findData("VALIDEE"))

        self.champ_campagne = QLineEdit(self)

        formulaire = QFormLayout()
        formulaire.addRow("Opération :", self.champ_operation)
        formulaire.addRow("Date :", self.champ_date)
        formulaire.addRow("Libellé :", self.champ_libelle)
        formulaire.addRow("Compte :", self.champ_compte)
        formulaire.addRow("Montant :", self.champ_montant)
        formulaire.addRow("Sens :", self.champ_sens)
        formulaire.addRow("Statut :", self.champ_statut)
        formulaire.addRow("Campagne :", self.champ_campagne)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if ecriture_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if ecriture_id is not None:
            self._charger(ecriture_id)
        else:
            self._prefiltrer_depuis_operation()

    def _charger_operations(self) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT id, date, libelle FROM operations_comptables ORDER BY date DESC, id DESC")
        while query.next():
            self.champ_operation.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _charger_comptes(self) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT numero, intitule FROM plan_comptable ORDER BY numero")
        while query.next():
            numero, intitule = query.value(0), query.value(1)
            self.champ_compte.addItem(f"{numero} — {intitule}", numero)

    def _charger(self, ecriture_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT operation_id, date, libelle, compte, montant, sens, statut, campagne "
            "FROM ecritures_comptables WHERE id = ?"
        )
        query.addBindValue(ecriture_id)
        query.exec()
        if not query.next():
            return

        self.champ_operation.blockSignals(True)
        index_operation = self.champ_operation.findData(query.value(0))
        if index_operation >= 0:
            self.champ_operation.setCurrentIndex(index_operation)
        self.champ_operation.blockSignals(False)

        self.champ_date.setDate(QDate.fromString(query.value(1), "yyyy-MM-dd"))
        self.champ_libelle.setText(query.value(2))
        index_compte = self.champ_compte.findData(query.value(3))
        if index_compte >= 0:
            self.champ_compte.setCurrentIndex(index_compte)
        self.champ_montant.setValue(query.value(4))
        self.champ_sens.setCurrentIndex(self.champ_sens.findData(query.value(5)))
        self.champ_statut.setCurrentIndex(self.champ_statut.findData(query.value(6)))
        self.champ_campagne.setText(query.value(7) or "")

    def _prefiltrer_depuis_operation(self) -> None:
        """Reprend la date et le libellé de l'opération sélectionnée comme
        valeurs de départ (l'utilisateur peut les modifier) -- création uniquement."""
        query = QSqlQuery(self.db)
        query.prepare("SELECT date, libelle FROM operations_comptables WHERE id = ?")
        query.addBindValue(self.champ_operation.currentData())
        query.exec()
        if query.next():
            date_operation = QDate.fromString(query.value(0), "yyyy-MM-dd")
            if date_operation.isValid():
                self.champ_date.setDate(date_operation)
            if not self.champ_libelle.text():
                self.champ_libelle.setText(query.value(1))

    def _valider(self) -> None:
        if self.champ_operation.count() == 0:
            QMessageBox.warning(
                self, "Aucune opération", "Créez d'abord une opération comptable avant d'ajouter une écriture."
            )
            return
        if self.champ_compte.count() == 0:
            QMessageBox.warning(
                self, "Plan comptable vide", "Activez d'abord des comptes dans le plan comptable."
            )
            return

        libelle = self.champ_libelle.text().strip()
        if not libelle:
            QMessageBox.warning(self, "Champ manquant", "Le libellé est obligatoire.")
            return
        if self.champ_montant.value() <= 0:
            QMessageBox.warning(self, "Montant invalide", "Le montant doit être supérieur à zéro.")
            return

        query = QSqlQuery(self.db)
        if self.ecriture_id is None:
            query.prepare(
                "INSERT INTO ecritures_comptables "
                "(operation_id, date, libelle, compte, montant, sens, statut, campagne) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
        else:
            query.prepare(
                "UPDATE ecritures_comptables SET operation_id = ?, date = ?, libelle = ?, compte = ?, "
                "montant = ?, sens = ?, statut = ?, campagne = ? WHERE id = ?"
            )
        query.addBindValue(self.champ_operation.currentData())
        query.addBindValue(self.champ_date.date().toString("yyyy-MM-dd"))
        query.addBindValue(libelle)
        query.addBindValue(self.champ_compte.currentData())
        query.addBindValue(self.champ_montant.value())
        query.addBindValue(self.champ_sens.currentData())
        query.addBindValue(self.champ_statut.currentData())
        query.addBindValue(self.champ_campagne.text().strip() or None)
        if self.ecriture_id is not None:
            query.addBindValue(self.ecriture_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer l'écriture :\n{query.lastError().text()}")
            return

        self.accept()
