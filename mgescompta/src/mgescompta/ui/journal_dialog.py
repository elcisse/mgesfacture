"""Dialogue de création/modification d'un journal comptable."""
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

TYPE_LABELS: dict[str, str] = {
    "ACHATS": "Achats",
    "VENTES": "Ventes",
    "TRESORERIE": "Trésorerie",
    "GENERAL": "Opérations diverses",
    "SITUATION": "À-nouveaux",
}


class JournalDialog(QDialog):
    """journal_id=None -> création ; sinon -> modification du journal existant."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, journal_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.journal_id = journal_id
        self.setWindowTitle("Modifier le journal" if journal_id else "Nouveau journal")
        self.resize(380, 180)

        self.champ_type = QComboBox(self)
        for valeur, libelle in TYPE_LABELS.items():
            self.champ_type.addItem(libelle, valeur)
        self.champ_type.currentIndexChanged.connect(self._prefiltrer_intitule)

        self.champ_code = QLineEdit(self)
        self.champ_intitule = QLineEdit(self)

        formulaire = QFormLayout()
        formulaire.addRow("Type :", self.champ_type)
        formulaire.addRow("Code :", self.champ_code)
        formulaire.addRow("Intitulé :", self.champ_intitule)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if journal_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if journal_id is not None:
            self._charger(journal_id)
        else:
            self._prefiltrer_intitule()

    def _charger(self, journal_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare("SELECT type, code, intitule FROM code_journaux WHERE id = ?")
        query.addBindValue(journal_id)
        query.exec()
        if query.next():
            self.champ_type.setCurrentIndex(self.champ_type.findData(query.value(0)))
            self.champ_code.setText(query.value(1))
            self.champ_intitule.setText(query.value(2))

    def _prefiltrer_intitule(self) -> None:
        if self.journal_id is None:
            self.champ_intitule.setText(TYPE_LABELS[self.champ_type.currentData()])

    def _valider(self) -> None:
        code = self.champ_code.text().strip()
        intitule = self.champ_intitule.text().strip()
        if not code or not intitule:
            QMessageBox.warning(self, "Champs manquants", "Le code et l'intitulé sont obligatoires.")
            return

        query = QSqlQuery(self.db)
        if self.journal_id is None:
            query.prepare("INSERT INTO code_journaux (type, code, intitule) VALUES (?, ?, ?)")
            query.addBindValue(self.champ_type.currentData())
            query.addBindValue(code)
            query.addBindValue(intitule)
        else:
            query.prepare("UPDATE code_journaux SET type = ?, code = ?, intitule = ? WHERE id = ?")
            query.addBindValue(self.champ_type.currentData())
            query.addBindValue(code)
            query.addBindValue(intitule)
            query.addBindValue(self.journal_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le journal :\n{query.lastError().text()}")
            return

        self.accept()
