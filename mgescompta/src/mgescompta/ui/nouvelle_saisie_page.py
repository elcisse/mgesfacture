"""Écran de saisie guidée : l'employé choisit une opération courante en
langage clair, l'application résout elle-même les comptes et le sens
débit/crédit. Aucune connaissance comptable requise."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtSql import QSqlDatabase, QSqlQuery, QSqlQueryModel
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from mgescompta.support.saisie import SaisieInvalideError, creer_operation_depuis_modele

TIERS_LABELS: dict[str, str] = {
    "ADHERENT": "Adhérent concerné",
    "FOURNISSEUR": "Fournisseur concerné",
    "SALARIE": "Salarié concerné",
    "AUTRE": "Tiers concerné",
}


class NouvelleSaisiePage(QWidget):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self._modeles: dict[str, dict] = {}

        self.champ_modele = QComboBox(self)
        self._charger_modeles()
        self.champ_modele.currentIndexChanged.connect(self._adapter_formulaire)

        self.champ_date = QDateEdit(QDate.currentDate(), self)
        self.champ_date.setCalendarPopup(True)
        self.champ_date.setDisplayFormat("dd/MM/yyyy")

        self.champ_montant = QDoubleSpinBox(self)
        self.champ_montant.setRange(1, 999_999_999)
        self.champ_montant.setDecimals(0)
        self.champ_montant.setSuffix(" FCFA")

        self.champ_mode_paiement = QComboBox(self)
        self.champ_mode_paiement.addItem("Espèces", "CAISSE")
        self.champ_mode_paiement.addItem("Banque", "BANQUE")

        self.champ_tiers = QComboBox(self)
        self.champ_tiers.setEditable(True)
        self.champ_tiers.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completeur_tiers = QCompleter(self.champ_tiers.model(), self.champ_tiers)
        completeur_tiers.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completeur_tiers.setFilterMode(Qt.MatchFlag.MatchContains)
        completeur_tiers.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.champ_tiers.setCompleter(completeur_tiers)

        self.champ_complement = QLineEdit(self)
        self.champ_piece = QLineEdit(self)

        self.bouton_enregistrer = QPushButton("Enregistrer", self)
        self.bouton_enregistrer.clicked.connect(self._enregistrer)

        self.formulaire = QFormLayout()
        self.formulaire.addRow("Type d'opération :", self.champ_modele)
        self.formulaire.addRow("Date :", self.champ_date)
        self.formulaire.addRow("Montant :", self.champ_montant)
        self.formulaire.addRow("Mode de paiement :", self.champ_mode_paiement)
        self.formulaire.addRow("Concerne :", self.champ_tiers)
        self.formulaire.addRow("Précision (optionnel) :", self.champ_complement)
        self.formulaire.addRow("Référence pièce (optionnel) :", self.champ_piece)
        self.formulaire.addRow("", self.bouton_enregistrer)

        self.modele_recent = QSqlQueryModel(self)
        self.vue_recente = QTableView(self)
        self.vue_recente.setModel(self.modele_recent)
        self.vue_recente.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.vue_recente.setAlternatingRowColors(True)
        self.vue_recente.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._rafraichir_recentes()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Nouvelle saisie</h2>"))
        layout.addLayout(self.formulaire)
        layout.addWidget(QLabel("<b>Dernières saisies</b>"))
        layout.addWidget(self.vue_recente, stretch=1)

        self._adapter_formulaire()

    # -- Chargement / adaptation du formulaire ---------------------------

    def _charger_modeles(self) -> None:
        query = QSqlQuery(self.db)
        query.exec(
            "SELECT code, nom, necessite_tiers, necessite_mode_paiement FROM modeles_saisie "
            "WHERE actif = 1 ORDER BY ordre_affichage"
        )
        while query.next():
            code, nom, necessite_tiers, necessite_mode_paiement = (
                query.value(0), query.value(1), query.value(2), bool(query.value(3))
            )
            self._modeles[code] = {
                "nom": nom,
                "necessite_tiers": necessite_tiers or None,
                "necessite_mode_paiement": necessite_mode_paiement,
            }
            self.champ_modele.addItem(nom, code)

    def _adapter_formulaire(self) -> None:
        code = self.champ_modele.currentData()
        infos = self._modeles.get(code, {})

        self._afficher_ligne(self.champ_mode_paiement, infos.get("necessite_mode_paiement", False))

        type_tiers = infos.get("necessite_tiers")
        self._afficher_ligne(self.champ_tiers, type_tiers is not None)
        if type_tiers is not None:
            self.formulaire.labelForField(self.champ_tiers).setText(f"{TIERS_LABELS.get(type_tiers, 'Tiers concerné')} :")
            self._charger_tiers(type_tiers)

    def _afficher_ligne(self, champ: QWidget, visible: bool) -> None:
        champ.setVisible(visible)
        label = self.formulaire.labelForField(champ)
        if label is not None:
            label.setVisible(visible)

    def _charger_tiers(self, type_tiers: str) -> None:
        self.champ_tiers.clear()
        self.champ_tiers.addItem("— Aucun —", None)
        query = QSqlQuery(self.db)
        query.prepare("SELECT id, numero, intitule FROM plan_tiers WHERE type = ? AND actif = 1 ORDER BY numero")
        query.addBindValue(type_tiers)
        query.exec()
        while query.next():
            self.champ_tiers.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    # -- Enregistrement ----------------------------------------------------

    def _enregistrer(self) -> None:
        code = self.champ_modele.currentData()
        if code is None:
            QMessageBox.warning(self, "Aucun modèle", "Aucun modèle de saisie n'est disponible.")
            return

        infos = self._modeles[code]
        mode_paiement = self.champ_mode_paiement.currentData() if infos["necessite_mode_paiement"] else None
        tiers_id = self.champ_tiers.currentData() if infos["necessite_tiers"] else None

        try:
            resultat = creer_operation_depuis_modele(
                self.db,
                code,
                self.champ_date.date().toString("yyyy-MM-dd"),
                self.champ_montant.value(),
                mode_paiement=mode_paiement,
                tiers_id=tiers_id,
                libelle_complement=self.champ_complement.text().strip() or None,
                piece_reference=self.champ_piece.text().strip() or None,
            )
        except SaisieInvalideError as erreur:
            QMessageBox.warning(self, "Saisie impossible", str(erreur))
            return

        QMessageBox.information(
            self, "Saisie enregistrée",
            f"Opération créée et validée automatiquement : {resultat.libelle}",
        )

        self.champ_montant.setValue(0.01)
        self.champ_complement.clear()
        self.champ_piece.clear()
        if self.champ_tiers.count() > 0:
            self.champ_tiers.setCurrentIndex(0)
        self._rafraichir_recentes()

    def refresh(self) -> None:
        self._adapter_formulaire()
        self._rafraichir_recentes()

    def _rafraichir_recentes(self) -> None:
        self.modele_recent.setQuery(
            "SELECT o.date AS Date, j.code AS Journal, o.libelle AS Libellé, o.statut AS Statut "
            "FROM operations_comptables o "
            "JOIN code_journaux j ON j.id = o.journal_id "
            "ORDER BY o.id DESC LIMIT 10",
            self.db,
        )
