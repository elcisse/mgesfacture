"""Dialogue de règlement groupé d'un tiers : un seul chèque (montant libre,
inférieur ou supérieur au solde total) réparti sur plusieurs factures --
automatiquement (la plus ancienne d'abord) ou ajusté manuellement facture
par facture."""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mgescompta.support.factures import (
    FactureInvalideError,
    factures_a_regler,
    reglement_groupe_tiers,
    repartir_fifo,
)
from mgescompta.support.formatage import formater_montant

COLONNES = ["N° facture", "Date", "Montant", "Solde", "Montant à appliquer"]
MODES_LABELS: list[tuple[str, str]] = [
    ("ESPECES", "Espèces"),
    ("CHEQUE", "Chèque"),
    ("VIREMENT", "Virement bancaire"),
    ("MOBILE_MONEY", "Mobile Money"),
]


class FactureReglementGroupeDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None, tiers_id: int) -> None:
        super().__init__(parent)
        self.db = db
        self.tiers_id = tiers_id
        self.setWindowTitle("Règlement groupé du tiers")
        self.resize(640, 480)

        query = QSqlQuery(db)
        query.prepare("SELECT numero, intitule FROM plan_tiers WHERE id = ?")
        query.addBindValue(tiers_id)
        query.exec()
        query.next()
        numero_tiers, intitule_tiers = query.value(0), query.value(1)

        self.factures = factures_a_regler(db, tiers_id)
        self.solde_total = round(sum(f["solde"] for f in self.factures), 2)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{numero_tiers} — {intitule_tiers}</b>"))
        layout.addWidget(QLabel(f"Solde total dû : {formater_montant(self.solde_total)}"))

        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLONNES))
        self.table.setHorizontalHeaderLabels(COLONNES)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setRowCount(len(self.factures))

        self.champs_montant: dict[int, QDoubleSpinBox] = {}
        for row, facture in enumerate(self.factures):
            self.table.setItem(row, 0, QTableWidgetItem(facture["numero_facture"]))
            self.table.setItem(row, 1, QTableWidgetItem(facture["date_facture"]))
            self.table.setItem(row, 2, QTableWidgetItem(formater_montant(facture["montant"])))
            self.table.setItem(row, 3, QTableWidgetItem(formater_montant(facture["solde"])))

            champ = QDoubleSpinBox(self)
            champ.setRange(0, facture["solde"])
            champ.setDecimals(0)
            champ.setSuffix(" FCFA")
            champ.valueChanged.connect(self._recalculer_total_reparti)
            self.table.setCellWidget(row, 4, champ)
            self.champs_montant[facture["id"]] = champ

        layout.addWidget(self.table)

        formulaire = QFormLayout()

        self.champ_montant_cheque = QDoubleSpinBox(self)
        self.champ_montant_cheque.setRange(1, 999_999_999)
        self.champ_montant_cheque.setDecimals(0)
        self.champ_montant_cheque.setSuffix(" FCFA")
        self.champ_montant_cheque.setValue(self.solde_total if self.solde_total > 0 else 1)
        self.champ_montant_cheque.valueChanged.connect(self._sur_changement_montant_cheque)
        formulaire.addRow("Montant du chèque :", self.champ_montant_cheque)

        self.champ_auto = QCheckBox("Répartition automatique (la plus ancienne facture d'abord)", self)
        self.champ_auto.setChecked(True)
        self.champ_auto.toggled.connect(self._sur_changement_mode_repartition)
        formulaire.addRow("", self.champ_auto)

        self.champ_date = QDateEdit(QDate.currentDate(), self)
        self.champ_date.setCalendarPopup(True)
        self.champ_date.setDisplayFormat("dd/MM/yyyy")
        formulaire.addRow("Date de règlement :", self.champ_date)

        self.champ_mode_paiement = QComboBox(self)
        for valeur, libelle in MODES_LABELS:
            self.champ_mode_paiement.addItem(libelle, valeur)
        self.champ_mode_paiement.setCurrentIndex(1)  # Chèque, le cas d'usage le plus courant ici
        formulaire.addRow("Mode de paiement :", self.champ_mode_paiement)

        self.champ_banque_operateur = QLineEdit(self)
        self.champ_banque_operateur.setPlaceholderText("Ex. Ecobank, Orange Money…")
        formulaire.addRow("Banque / opérateur (facultatif) :", self.champ_banque_operateur)

        self.champ_numero_compte = QLineEdit(self)
        self.champ_numero_compte.setPlaceholderText("N° de compte bancaire ou mobile")
        formulaire.addRow("N° de compte (facultatif) :", self.champ_numero_compte)

        self.champ_reference = QLineEdit(self)
        self.champ_reference.setPlaceholderText("N° de chèque ou référence de transaction")
        formulaire.addRow("Référence (facultatif) :", self.champ_reference)

        layout.addLayout(formulaire)

        self.label_total = QLabel(self)
        layout.addWidget(self.label_total)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        bouton_valider = boutons.addButton("Régler", QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)
        layout.addWidget(boutons)

        self._appliquer_repartition_auto()

    def _sur_changement_montant_cheque(self) -> None:
        if self.champ_auto.isChecked():
            self._appliquer_repartition_auto()
        else:
            self._recalculer_total_reparti()

    def _sur_changement_mode_repartition(self, coche: bool) -> None:
        for champ in self.champs_montant.values():
            champ.setEnabled(not coche)
        if coche:
            self._appliquer_repartition_auto()

    def _appliquer_repartition_auto(self) -> None:
        allocations = repartir_fifo(self.factures, self.champ_montant_cheque.value())
        for facture_id, champ in self.champs_montant.items():
            champ.blockSignals(True)
            champ.setValue(allocations.get(facture_id, 0.0))
            champ.blockSignals(False)
        self._recalculer_total_reparti()

    def _recalculer_total_reparti(self) -> None:
        total_reparti = round(sum(champ.value() for champ in self.champs_montant.values()), 2)
        montant_cheque = self.champ_montant_cheque.value()
        surplus = round(montant_cheque - total_reparti, 2)
        texte = (
            f"Total réparti sur les factures : {formater_montant(total_reparti)} "
            f"/ Montant du chèque : {formater_montant(montant_cheque)}"
        )
        if surplus > 0.001:
            texte += f"  (surplus de {formater_montant(surplus)} non affecté -- restera en crédit sur le compte du tiers)"
        self.label_total.setText(texte)

    def _valider(self) -> None:
        allocations = {facture_id: champ.value() for facture_id, champ in self.champs_montant.items()}
        try:
            reglement_groupe_tiers(
                self.db,
                self.tiers_id,
                allocations,
                self.champ_montant_cheque.value(),
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
