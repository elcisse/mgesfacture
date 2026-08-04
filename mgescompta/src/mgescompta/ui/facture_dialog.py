"""Dialogue de création/modification d'une facture fournisseur (document
commercial, distinct de sa comptabilisation -- voir support/factures.py)."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
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

from mgescompta.support.formatage import formater_montant
from mgescompta.support.reference_interne import generer_reference_interne


class FactureDialog(QDialog):
    """facture_id=None -> création ; sinon -> modification (n'est ouvert par
    l'UI que pour des factures pas encore comptabilisées)."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, facture_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.facture_id = facture_id
        self.setWindowTitle("Modifier la facture" if facture_id else "Nouvelle facture")
        self.resize(440, 380)

        self.champ_tiers = QComboBox(self)
        self.champ_tiers.setEditable(True)
        self.champ_tiers.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._charger_fournisseurs()
        completeur = QCompleter(self.champ_tiers.model(), self.champ_tiers)
        completeur.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completeur.setFilterMode(Qt.MatchFlag.MatchContains)
        completeur.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.champ_tiers.setCompleter(completeur)
        if facture_id is None:
            self.champ_tiers.currentIndexChanged.connect(self._suggerer_compte_charge)

        self.champ_reference_interne = QLineEdit(self)
        self.champ_reference_interne.setReadOnly(True)
        self.champ_reference_interne.setPlaceholderText("(attribuée automatiquement à l'enregistrement)")

        self.champ_numero = QLineEdit(self)
        self.champ_date_facture = QDateEdit(QDate.currentDate(), self)
        self.champ_date_facture.setCalendarPopup(True)
        self.champ_date_facture.setDisplayFormat("dd/MM/yyyy")

        self.champ_date_echeance = QDateEdit(QDate.currentDate(), self)
        self.champ_date_echeance.setCalendarPopup(True)
        self.champ_date_echeance.setDisplayFormat("dd/MM/yyyy")

        self.champ_compte_charge = QComboBox(self)
        self._charger_comptes_charge()

        self.champ_montant = QDoubleSpinBox(self)
        self.champ_montant.setRange(1, 999_999_999)
        self.champ_montant.setDecimals(0)
        self.champ_montant.setSuffix(" FCFA")

        self.champ_libelle = QLineEdit(self)

        formulaire = QFormLayout()
        formulaire.addRow("Fournisseur :", self.champ_tiers)
        formulaire.addRow("Référence interne :", self.champ_reference_interne)
        formulaire.addRow("N° de facture :", self.champ_numero)
        formulaire.addRow("Date de la facture :", self.champ_date_facture)
        formulaire.addRow("Échéance :", self.champ_date_echeance)
        formulaire.addRow("Compte de charge :", self.champ_compte_charge)
        formulaire.addRow("Montant :", self.champ_montant)
        formulaire.addRow("Libellé (optionnel) :", self.champ_libelle)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if facture_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if facture_id is not None:
            self._charger(facture_id)
        else:
            self._suggerer_compte_charge()

    def _charger_fournisseurs(self) -> None:
        query = QSqlQuery(self.db)
        query.exec(
            "SELECT id, numero, intitule FROM plan_tiers WHERE type = 'FOURNISSEUR' AND actif = 1 ORDER BY intitule"
        )
        while query.next():
            self.champ_tiers.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _charger_comptes_charge(self) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT numero, intitule FROM plan_comptable WHERE nature = 'CHARGE' ORDER BY numero")
        while query.next():
            self.champ_compte_charge.addItem(f"{query.value(0)} — {query.value(1)}", query.value(0))

    def _suggerer_compte_charge(self) -> None:
        """Si le fournisseur est un prestataire de santé classifié, le
        compte de prise en charge (652000) est le plus probable."""
        tiers_id = self.champ_tiers.currentData()
        if tiers_id is None:
            return
        query = QSqlQuery(self.db)
        query.prepare("SELECT classification_id FROM plan_tiers WHERE id = ?")
        query.addBindValue(tiers_id)
        query.exec()
        if query.next() and query.value(0):
            index = self.champ_compte_charge.findData("652000")
            if index >= 0:
                self.champ_compte_charge.setCurrentIndex(index)

    def _charger(self, facture_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT tiers_id, numero_facture, date_facture, date_echeance, compte_charge, montant, libelle, "
            "reference_interne "
            "FROM factures WHERE id = ?"
        )
        query.addBindValue(facture_id)
        query.exec()
        if not query.next():
            return
        index_tiers = self.champ_tiers.findData(query.value(0))
        if index_tiers >= 0:
            self.champ_tiers.setCurrentIndex(index_tiers)
        self.champ_numero.setText(query.value(1))
        self.champ_date_facture.setDate(QDate.fromString(query.value(2), "yyyy-MM-dd"))
        if query.value(3):
            self.champ_date_echeance.setDate(QDate.fromString(query.value(3), "yyyy-MM-dd"))
        index_compte = self.champ_compte_charge.findData(query.value(4))
        if index_compte >= 0:
            self.champ_compte_charge.setCurrentIndex(index_compte)
        self.champ_montant.setValue(query.value(5))
        self.champ_libelle.setText(query.value(6) or "")
        self.champ_reference_interne.setText(query.value(7) or "")

    def _valider(self) -> None:
        if self.champ_tiers.count() == 0:
            QMessageBox.warning(self, "Aucun fournisseur", "Créez d'abord un tiers de type Fournisseur.")
            return
        tiers_id = self.champ_tiers.currentData()
        if tiers_id is None:
            QMessageBox.warning(self, "Fournisseur manquant", "Sélectionnez un fournisseur dans la liste.")
            return

        numero = self.champ_numero.text().strip()
        if not numero:
            QMessageBox.warning(self, "Champ manquant", "Le numéro de facture est obligatoire.")
            return
        if self.champ_compte_charge.count() == 0:
            QMessageBox.warning(
                self, "Plan comptable vide", "Activez d'abord un compte de charge dans le plan comptable."
            )
            return

        montant = self.champ_montant.value()
        annee_mois = self.champ_date_facture.date().toString("yyyy-MM")

        if not self._confirmer_si_doublon(tiers_id, montant, annee_mois):
            return

        query = QSqlQuery(self.db)
        if self.facture_id is None:
            query.prepare(
                "INSERT INTO factures "
                "(reference_interne, tiers_id, numero_facture, date_facture, annee_mois, date_echeance, "
                "compte_charge, libelle, montant) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            # Référence lisible, attribuée à la création seulement -- jamais
            # régénérée si la facture est modifiée ensuite (même si sa date
            # change d'année). Préfixe FC- : cette facture est saisie
            # directement ici, pas importée de mgesfacture.
            query.addBindValue(generer_reference_interne(self.db, self.champ_date_facture.date().year()))
        else:
            query.prepare(
                "UPDATE factures SET tiers_id = ?, numero_facture = ?, date_facture = ?, annee_mois = ?, "
                "date_echeance = ?, compte_charge = ?, libelle = ?, montant = ? WHERE id = ?"
            )
        query.addBindValue(tiers_id)
        query.addBindValue(numero)
        query.addBindValue(self.champ_date_facture.date().toString("yyyy-MM-dd"))
        # Champ "année-mois" dérivé automatiquement de la date de la facture,
        # pour permettre le filtrage/regroupement par période.
        query.addBindValue(annee_mois)
        query.addBindValue(self.champ_date_echeance.date().toString("yyyy-MM-dd"))
        query.addBindValue(self.champ_compte_charge.currentData())
        query.addBindValue(self.champ_libelle.text().strip() or None)
        query.addBindValue(montant)
        if self.facture_id is not None:
            query.addBindValue(self.facture_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer la facture :\n{query.lastError().text()}")
            return

        self.accept()

    def _confirmer_si_doublon(self, tiers_id: int, montant: float, annee_mois: str) -> bool:
        """Averti (sans bloquer) si ce fournisseur a déjà une facture de même
        montant, ou une facture sur la même période -- doublon de saisie
        fréquent. Retourne False si l'utilisateur annule."""
        requete = (
            "SELECT numero_facture, date_facture, montant, annee_mois FROM factures "
            "WHERE tiers_id = ? AND (ROUND(montant, 2) = ROUND(?, 2) OR annee_mois = ?)"
        )
        if self.facture_id is not None:
            requete += " AND id != ?"
        query = QSqlQuery(self.db)
        query.prepare(requete)
        query.addBindValue(tiers_id)
        query.addBindValue(montant)
        query.addBindValue(annee_mois)
        if self.facture_id is not None:
            query.addBindValue(self.facture_id)
        query.exec()

        lignes = []
        while query.next():
            numero_f, date_f, montant_f, annee_mois_f = (query.value(i) for i in range(4))
            raisons = []
            if round(montant_f, 2) == round(montant, 2):
                raisons.append("même montant")
            if annee_mois_f == annee_mois:
                raisons.append("même période")
            lignes.append(f"- N° {numero_f}, du {date_f}, montant {formater_montant(montant_f)} ({' et '.join(raisons)})")

        if not lignes:
            return True

        reponse = QMessageBox.question(
            self,
            "Facture potentiellement en double",
            "Ce fournisseur a déjà une ou plusieurs factures similaires :\n\n"
            + "\n".join(lignes)
            + "\n\nVoulez-vous vraiment enregistrer cette facture ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reponse == QMessageBox.StandardButton.Yes
