"""Dialogue de règlement (total ou partiel) d'une facture déjà comptabilisée."""
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
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from mgescompta.support.factures import FactureInvalideError, reglement_facture
from mgescompta.support.formatage import formater_montant

MODES_LABELS: list[tuple[str, str]] = [
    ("ESPECES", "Espèces"),
    ("CHEQUE", "Chèque"),
    ("VIREMENT", "Virement bancaire"),
    ("MOBILE_MONEY", "Mobile Money"),
]


class FactureReglementDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None, facture_id: int) -> None:
        super().__init__(parent)
        self.db = db
        self.facture_id = facture_id
        self.setWindowTitle("Régler la facture")
        self.resize(400, 320)

        query = QSqlQuery(db)
        query.prepare(
            "SELECT f.numero_facture, f.montant, f.montant_regle, t.intitule "
            "FROM factures f JOIN plan_tiers t ON t.id = f.tiers_id WHERE f.id = ?"
        )
        query.addBindValue(facture_id)
        query.exec()
        query.next()
        numero, montant_total, montant_regle, tiers_intitule = (
            query.value(0), query.value(1), query.value(2), query.value(3)
        )
        self.solde = round(montant_total - montant_regle, 2)

        self.champ_date = QDateEdit(QDate.currentDate(), self)
        self.champ_date.setCalendarPopup(True)
        self.champ_date.setDisplayFormat("dd/MM/yyyy")

        self.champ_montant = QDoubleSpinBox(self)
        self.champ_montant.setRange(1, max(1, self.solde))
        self.champ_montant.setDecimals(0)
        self.champ_montant.setSuffix(" FCFA")
        self.champ_montant.setValue(self.solde)

        self.champ_mode_paiement = QComboBox(self)
        for valeur, libelle in MODES_LABELS:
            self.champ_mode_paiement.addItem(libelle, valeur)

        self.champ_banque_operateur = QLineEdit(self)
        self.champ_banque_operateur.setPlaceholderText("Ex. Ecobank, Orange Money…")
        self.champ_numero_compte = QLineEdit(self)
        self.champ_numero_compte.setPlaceholderText("N° de compte bancaire ou mobile")
        self.champ_reference = QLineEdit(self)
        self.champ_reference.setPlaceholderText("N° de chèque ou référence de transaction")

        formulaire = QFormLayout()
        formulaire.addRow("Facture :", QLabel(f"{numero} — {tiers_intitule}"))
        formulaire.addRow("Solde restant dû :", QLabel(formater_montant(self.solde)))
        formulaire.addRow("Date de règlement :", self.champ_date)
        formulaire.addRow("Montant réglé :", self.champ_montant)
        formulaire.addRow("Mode de paiement :", self.champ_mode_paiement)
        formulaire.addRow("Banque / opérateur (facultatif) :", self.champ_banque_operateur)
        formulaire.addRow("N° de compte (facultatif) :", self.champ_numero_compte)
        formulaire.addRow("Référence (facultatif) :", self.champ_reference)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        bouton_valider = boutons.addButton("Régler", QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

    def _valider(self) -> None:
        try:
            reglement_facture(
                self.db,
                self.facture_id,
                self.champ_montant.value(),
                self.champ_mode_paiement.currentData(),
                self.champ_date.date().toString("yyyy-MM-dd"),
                self.champ_banque_operateur.text().strip() or None,
                self.champ_numero_compte.text().strip() or None,
                self.champ_reference.text().strip() or None,
            )
        except FactureInvalideError as erreur:
            QMessageBox.warning(self, "Règlement impossible", str(erreur))
            return

        self.accept()
