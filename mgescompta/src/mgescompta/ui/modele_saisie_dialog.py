"""Dialogue de création/modification d'un modèle de saisie, avec édition de
ses lignes débit/crédit (voir support/saisie.py pour leur résolution)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

JOURNAL_LABELS: dict[str, str] = {
    "ACHATS": "Achats",
    "VENTES": "Ventes",
    "TRESORERIE": "Trésorerie",
    "GENERAL": "Opérations diverses",
    "SITUATION": "À-nouveaux",
}
TIERS_LABELS: dict[str, str] = {
    "ADHERENT": "Adhérent",
    "FOURNISSEUR": "Fournisseur",
    "SALARIE": "Salarié",
    "AUTRE": "Autre",
}
SENS_LABELS: dict[str, str] = {"DEBIT": "Débit", "CREDIT": "Crédit"}
# TIERS non proposé : non résolu par le moteur de saisie (voir support/saisie.py).
TYPE_COMPTE_LABELS: dict[str, str] = {"FIXE": "Compte fixe", "TRESORERIE": "Trésorerie (caisse/banque)"}

COL_SENS, COL_TYPE, COL_COMPTE = range(3)


class ModeleSaisieDialog(QDialog):
    """modele_id=None -> création ; sinon -> modification du modèle et de ses lignes."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, modele_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.modele_id = modele_id
        self.setWindowTitle("Modifier le modèle de saisie" if modele_id else "Nouveau modèle de saisie")
        self.resize(560, 560)

        self.champ_code = QLineEdit(self)
        self.champ_nom = QLineEdit(self)

        self.champ_journal = QComboBox(self)
        for valeur, libelle in JOURNAL_LABELS.items():
            self.champ_journal.addItem(libelle, valeur)

        self.champ_tiers = QComboBox(self)
        self.champ_tiers.addItem("— Aucun —", None)
        for valeur, libelle in TIERS_LABELS.items():
            self.champ_tiers.addItem(libelle, valeur)

        self.champ_mode_paiement = QCheckBox("Ce modèle nécessite un mode de paiement (caisse/banque)", self)
        self.champ_actif = QCheckBox("Actif", self)
        self.champ_actif.setChecked(True)

        self.champ_ordre = QSpinBox(self)
        self.champ_ordre.setRange(0, 9999)

        self.champ_note = QLineEdit(self)

        formulaire = QFormLayout()
        formulaire.addRow("Code :", self.champ_code)
        formulaire.addRow("Nom :", self.champ_nom)
        formulaire.addRow("Journal :", self.champ_journal)
        formulaire.addRow("Tiers concerné :", self.champ_tiers)
        formulaire.addRow("", self.champ_mode_paiement)
        formulaire.addRow("Ordre d'affichage :", self.champ_ordre)
        formulaire.addRow("Note :", self.champ_note)
        formulaire.addRow("", self.champ_actif)

        self.table_lignes = QTableWidget(self)
        self.table_lignes.setColumnCount(3)
        self.table_lignes.setHorizontalHeaderLabels(["Sens", "Type de compte", "Compte (si fixe)"])
        self.table_lignes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_lignes.verticalHeader().setVisible(False)

        bouton_ajouter_ligne = QPushButton("Ajouter une ligne", self)
        bouton_ajouter_ligne.clicked.connect(lambda: self._ajouter_ligne())
        bouton_retirer_ligne = QPushButton("Retirer la ligne sélectionnée", self)
        bouton_retirer_ligne.clicked.connect(self._retirer_ligne)

        boutons_lignes = QHBoxLayout()
        boutons_lignes.addWidget(bouton_ajouter_ligne)
        boutons_lignes.addWidget(bouton_retirer_ligne)
        boutons_lignes.addStretch(1)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if modele_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(QLabel("<b>Lignes débit/crédit</b> (même montant saisi pour toutes les lignes)"))
        layout.addWidget(self.table_lignes)
        layout.addLayout(boutons_lignes)
        layout.addWidget(boutons)

        if modele_id is not None:
            self._charger(modele_id)
        else:
            self._ajouter_ligne("DEBIT")
            self._ajouter_ligne("CREDIT")

    # -- Lignes ------------------------------------------------------------

    def _ajouter_ligne(self, sens: str = "DEBIT", type_compte: str = "FIXE", compte_code: str | None = None) -> None:
        row = self.table_lignes.rowCount()
        self.table_lignes.insertRow(row)

        combo_sens = QComboBox(self.table_lignes)
        for valeur, libelle in SENS_LABELS.items():
            combo_sens.addItem(libelle, valeur)
        combo_sens.setCurrentIndex(combo_sens.findData(sens))
        self.table_lignes.setCellWidget(row, COL_SENS, combo_sens)

        combo_type = QComboBox(self.table_lignes)
        for valeur, libelle in TYPE_COMPTE_LABELS.items():
            combo_type.addItem(libelle, valeur)
        combo_type.setCurrentIndex(combo_type.findData(type_compte))
        self.table_lignes.setCellWidget(row, COL_TYPE, combo_type)

        combo_compte = QComboBox(self.table_lignes)
        self._charger_comptes(combo_compte)
        if compte_code is not None:
            index = combo_compte.findData(compte_code)
            if index >= 0:
                combo_compte.setCurrentIndex(index)
        self.table_lignes.setCellWidget(row, COL_COMPTE, combo_compte)

        combo_type.currentIndexChanged.connect(
            lambda: combo_compte.setEnabled(combo_type.currentData() == "FIXE")
        )
        combo_compte.setEnabled(type_compte == "FIXE")

    def _retirer_ligne(self) -> None:
        row = self.table_lignes.currentRow()
        if row >= 0:
            self.table_lignes.removeRow(row)

    def _charger_comptes(self, combo: QComboBox) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT numero, intitule FROM plan_comptable ORDER BY numero")
        while query.next():
            combo.addItem(f"{query.value(0)} — {query.value(1)}", query.value(0))

    # -- Chargement / validation --------------------------------------------

    def _charger(self, modele_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT code, nom, journal_type, necessite_tiers, necessite_mode_paiement, "
            "actif, ordre_affichage, note FROM modeles_saisie WHERE id = ?"
        )
        query.addBindValue(modele_id)
        query.exec()
        if not query.next():
            return
        self.champ_code.setText(query.value(0))
        self.champ_nom.setText(query.value(1))
        self.champ_journal.setCurrentIndex(self.champ_journal.findData(query.value(2)))
        self.champ_tiers.setCurrentIndex(self.champ_tiers.findData(query.value(3)))
        self.champ_mode_paiement.setChecked(bool(query.value(4)))
        self.champ_actif.setChecked(bool(query.value(5)))
        self.champ_ordre.setValue(query.value(6) or 0)
        self.champ_note.setText(query.value(7) or "")

        lignes = QSqlQuery(self.db)
        lignes.prepare(
            "SELECT sens, type_compte, compte_code FROM modeles_saisie_lignes "
            "WHERE modele_id = ? ORDER BY ordre"
        )
        lignes.addBindValue(modele_id)
        lignes.exec()
        while lignes.next():
            self._ajouter_ligne(lignes.value(0), lignes.value(1), lignes.value(2))

    def _valider(self) -> None:
        code = self.champ_code.text().strip()
        nom = self.champ_nom.text().strip()
        if not code or not nom:
            QMessageBox.warning(self, "Champs manquants", "Le code et le nom sont obligatoires.")
            return

        if self.table_lignes.rowCount() < 2:
            QMessageBox.warning(self, "Lignes insuffisantes", "Un modèle doit comporter au moins deux lignes.")
            return

        lignes: list[tuple[str, str, str | None]] = []
        for row in range(self.table_lignes.rowCount()):
            sens = self.table_lignes.cellWidget(row, COL_SENS).currentData()
            type_compte = self.table_lignes.cellWidget(row, COL_TYPE).currentData()
            combo_compte = self.table_lignes.cellWidget(row, COL_COMPTE)
            compte_code = combo_compte.currentData() if type_compte == "FIXE" else None
            if type_compte == "FIXE" and compte_code is None:
                QMessageBox.warning(
                    self, "Compte manquant",
                    "Choisissez un compte pour chaque ligne de type « Compte fixe ».",
                )
                return
            lignes.append((sens, type_compte, compte_code))

        if not any(s == "DEBIT" for s, _, _ in lignes) or not any(s == "CREDIT" for s, _, _ in lignes):
            QMessageBox.warning(
                self, "Lignes déséquilibrées",
                "Le modèle doit comporter au moins une ligne au débit et une ligne au crédit.",
            )
            return
        if sum(1 for s, _, _ in lignes if s == "DEBIT") != sum(1 for s, _, _ in lignes if s == "CREDIT"):
            QMessageBox.warning(
                self, "Lignes déséquilibrées",
                "Toutes les lignes utilisant le même montant saisi, il doit y avoir autant de "
                "lignes au débit qu'au crédit.",
            )
            return

        necessite_tiers = self.champ_tiers.currentData()
        necessite_mode_paiement = 1 if self.champ_mode_paiement.isChecked() else 0
        actif = 1 if self.champ_actif.isChecked() else 0
        ordre = self.champ_ordre.value()
        note = self.champ_note.text().strip() or None
        journal_type = self.champ_journal.currentData()

        self.db.transaction()

        modele_query = QSqlQuery(self.db)
        if self.modele_id is None:
            modele_query.prepare(
                "INSERT INTO modeles_saisie "
                "(code, nom, journal_type, necessite_tiers, necessite_mode_paiement, actif, ordre_affichage, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
        else:
            modele_query.prepare(
                "UPDATE modeles_saisie SET code = ?, nom = ?, journal_type = ?, necessite_tiers = ?, "
                "necessite_mode_paiement = ?, actif = ?, ordre_affichage = ?, note = ? WHERE id = ?"
            )
        modele_query.addBindValue(code)
        modele_query.addBindValue(nom)
        modele_query.addBindValue(journal_type)
        modele_query.addBindValue(necessite_tiers)
        modele_query.addBindValue(necessite_mode_paiement)
        modele_query.addBindValue(actif)
        modele_query.addBindValue(ordre)
        modele_query.addBindValue(note)
        if self.modele_id is not None:
            modele_query.addBindValue(self.modele_id)

        if not modele_query.exec():
            self.db.rollback()
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le modèle :\n{modele_query.lastError().text()}")
            return

        modele_id = self.modele_id if self.modele_id is not None else modele_query.lastInsertId()

        delete_lignes = QSqlQuery(self.db)
        delete_lignes.prepare("DELETE FROM modeles_saisie_lignes WHERE modele_id = ?")
        delete_lignes.addBindValue(modele_id)
        if not delete_lignes.exec():
            self.db.rollback()
            QMessageBox.critical(self, "Erreur", f"Impossible de mettre à jour les lignes :\n{delete_lignes.lastError().text()}")
            return

        insert_ligne = QSqlQuery(self.db)
        insert_ligne.prepare(
            "INSERT INTO modeles_saisie_lignes (modele_id, ordre, sens, type_compte, compte_code) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        for ordre_ligne, (sens, type_compte, compte_code) in enumerate(lignes, start=1):
            insert_ligne.addBindValue(modele_id)
            insert_ligne.addBindValue(ordre_ligne)
            insert_ligne.addBindValue(sens)
            insert_ligne.addBindValue(type_compte)
            insert_ligne.addBindValue(compte_code)
            if not insert_ligne.exec():
                self.db.rollback()
                QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer une ligne :\n{insert_ligne.lastError().text()}")
                return

        self.db.commit()
        self.accept()
