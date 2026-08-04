"""Dialogue de création/modification d'une facture (simple enregistrement
documentaire -- aucune comptabilisation ni règlement dans cette appli)."""
from __future__ import annotations

import uuid

from PySide6.QtCore import QDate, Qt
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QCheckBox,
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

from mgesfacture.support.formatage import formater_montant
from mgesfacture.support.reference_interne import generer_reference_interne
from mgesfacture.ui.icone import icone_ronde_verte


class FactureDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, facture_id: int | None = None) -> None:
        super().__init__(parent)
        self.setWindowIcon(icone_ronde_verte())
        self.db = db
        self.facture_id = facture_id
        self.setWindowTitle("Modifier la facture" if facture_id else "Nouvelle facture")
        self.resize(440, 380)

        self.champ_tiers = QComboBox(self)
        self.champ_tiers.setEditable(True)
        self.champ_tiers.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._charger_tiers()
        completeur = QCompleter(self.champ_tiers.model(), self.champ_tiers)
        completeur.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completeur.setFilterMode(Qt.MatchFlag.MatchContains)
        completeur.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.champ_tiers.setCompleter(completeur)

        self.champ_reference_interne = QLineEdit(self)
        self.champ_reference_interne.setReadOnly(True)
        self.champ_reference_interne.setPlaceholderText("(attribuée automatiquement à l'enregistrement)")

        self.champ_numero = QLineEdit(self)
        self.champ_date_facture = QDateEdit(QDate.currentDate(), self)
        self.champ_date_facture.setCalendarPopup(True)
        self.champ_date_facture.setDisplayFormat("dd/MM/yyyy")

        self.champ_avec_echeance = QCheckBox("Définir une échéance", self)
        self.champ_date_echeance = QDateEdit(QDate.currentDate(), self)
        self.champ_date_echeance.setCalendarPopup(True)
        self.champ_date_echeance.setDisplayFormat("dd/MM/yyyy")
        self.champ_date_echeance.setEnabled(False)
        self.champ_avec_echeance.toggled.connect(self.champ_date_echeance.setEnabled)

        self.champ_montant = QDoubleSpinBox(self)
        self.champ_montant.setRange(1, 999_999_999)
        self.champ_montant.setDecimals(0)
        self.champ_montant.setSuffix(" FCFA")

        self.champ_libelle = QLineEdit(self)

        formulaire = QFormLayout()
        formulaire.addRow("Fournisseur (tiers) :", self.champ_tiers)
        formulaire.addRow("Référence interne :", self.champ_reference_interne)
        formulaire.addRow("N° de facture :", self.champ_numero)
        formulaire.addRow("Date de la facture :", self.champ_date_facture)
        formulaire.addRow("", self.champ_avec_echeance)
        formulaire.addRow("Échéance :", self.champ_date_echeance)
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

    def _charger_tiers(self) -> None:
        query = QSqlQuery(self.db)
        query.exec(
            "SELECT id, numero, intitule FROM tiers WHERE type = 'FOURNISSEUR' AND actif = 1 ORDER BY intitule"
        )
        while query.next():
            self.champ_tiers.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _charger(self, facture_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT tiers_id, numero_facture, date_facture, date_echeance, montant, libelle, reference_interne "
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
        date_echeance = query.value(3)
        if date_echeance:
            # NB: QSqlQuery.value() renvoie '' (pas None) pour un NULL texte.
            self.champ_avec_echeance.setChecked(True)
            self.champ_date_echeance.setDate(QDate.fromString(date_echeance, "yyyy-MM-dd"))
        self.champ_montant.setValue(query.value(4))
        self.champ_libelle.setText(query.value(5) or "")
        self.champ_reference_interne.setText(query.value(6) or "")

    def _valider(self) -> None:
        if self.champ_tiers.count() == 0:
            QMessageBox.warning(self, "Aucun tiers", "Créez d'abord un tiers de type Fournisseur.")
            return
        tiers_id = self.champ_tiers.currentData()
        if tiers_id is None:
            QMessageBox.warning(self, "Fournisseur manquant", "Sélectionnez un tiers dans la liste.")
            return

        numero = self.champ_numero.text().strip()
        if not numero:
            QMessageBox.warning(self, "Champ manquant", "Le numéro de facture est obligatoire.")
            return

        date_echeance = (
            self.champ_date_echeance.date().toString("yyyy-MM-dd") if self.champ_avec_echeance.isChecked() else None
        )
        montant = self.champ_montant.value()
        annee_mois = self.champ_date_facture.date().toString("yyyy-MM")

        if not self._confirmer_si_doublon(tiers_id, montant, annee_mois):
            return

        query = QSqlQuery(self.db)
        if self.facture_id is None:
            query.prepare(
                "INSERT INTO factures "
                "(uuid, reference_interne, tiers_id, numero_facture, date_facture, annee_mois, date_echeance, "
                "libelle, montant) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            # Identifiant globalement unique (pas l'id auto-incrémenté, qui
            # n'est unique que dans cette base) -- généré une seule fois à la
            # création, jamais régénéré, exporté comme clé d'idempotence pour
            # que l'import reste fiable même avec plusieurs machines.
            query.addBindValue(str(uuid.uuid4()))
            # Référence lisible, attribuée à la création seulement -- jamais
            # régénérée si la facture est modifiée ensuite (même si sa date
            # change d'année).
            query.addBindValue(generer_reference_interne(self.db, self.champ_date_facture.date().year()))
        else:
            query.prepare(
                "UPDATE factures SET tiers_id = ?, numero_facture = ?, date_facture = ?, annee_mois = ?, "
                "date_echeance = ?, libelle = ?, montant = ? WHERE id = ?"
            )
        query.addBindValue(tiers_id)
        query.addBindValue(numero)
        query.addBindValue(self.champ_date_facture.date().toString("yyyy-MM-dd"))
        # Champ "année-mois" dérivé automatiquement de la date de la facture,
        # pour permettre le filtrage/regroupement par période.
        query.addBindValue(annee_mois)
        query.addBindValue(date_echeance)
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
