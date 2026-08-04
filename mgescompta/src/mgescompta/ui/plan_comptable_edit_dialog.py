"""Dialogue de modification d'un compte activé dans le plan comptable :
intitulé, nature, report à nouveau, et activation/désactivation. Le numéro
n'est pas modifiable (identité du compte, référencée par les tiers et
écritures) ; il n'y a pas de mode création ici -- l'activation se fait
depuis le référentiel (voir SelectionComptesDialog)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from mgescompta.support.plan_comptable import NATURE_LABELS, REPORT_A_NOUVEAU_LABELS


class PlanComptableEditDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, plan_comptable_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.plan_comptable_id = plan_comptable_id
        self.setWindowTitle("Modifier le compte")
        self.resize(400, 220)

        self.champ_numero = QLabel(self)
        self.champ_intitule = QLineEdit(self)

        self.champ_nature = QComboBox(self)
        for valeur, libelle in NATURE_LABELS.items():
            self.champ_nature.addItem(libelle, valeur)

        self.champ_report = QComboBox(self)
        for valeur, libelle in REPORT_A_NOUVEAU_LABELS.items():
            self.champ_report.addItem(libelle, valeur)

        self.champ_actif = QCheckBox("Actif", self)

        formulaire = QFormLayout()
        formulaire.addRow("Numéro :", self.champ_numero)
        formulaire.addRow("Intitulé :", self.champ_intitule)
        formulaire.addRow("Nature :", self.champ_nature)
        formulaire.addRow("Report à nouveau :", self.champ_report)
        formulaire.addRow("", self.champ_actif)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        bouton_valider = boutons.addButton("Enregistrer", QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if plan_comptable_id is not None:
            self._charger(plan_comptable_id)

    def _charger(self, plan_comptable_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT numero, intitule, nature, report_a_nouveau, actif FROM plan_comptable WHERE id = ?"
        )
        query.addBindValue(plan_comptable_id)
        query.exec()
        if not query.next():
            return
        self.champ_numero.setText(query.value(0))
        self.champ_intitule.setText(query.value(1))
        self.champ_nature.setCurrentIndex(self.champ_nature.findData(query.value(2)))
        self.champ_report.setCurrentIndex(self.champ_report.findData(query.value(3)))
        self.champ_actif.setChecked(bool(query.value(4)))

    def _valider(self) -> None:
        intitule = self.champ_intitule.text().strip()
        if not intitule:
            QMessageBox.warning(self, "Champ manquant", "L'intitulé est obligatoire.")
            return

        query = QSqlQuery(self.db)
        query.prepare(
            "UPDATE plan_comptable SET intitule = ?, nature = ?, report_a_nouveau = ?, actif = ? WHERE id = ?"
        )
        query.addBindValue(intitule)
        query.addBindValue(self.champ_nature.currentData())
        query.addBindValue(self.champ_report.currentData())
        query.addBindValue(1 if self.champ_actif.isChecked() else 0)
        query.addBindValue(self.plan_comptable_id)
        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le compte :\n{query.lastError().text()}")
            return

        self.accept()
