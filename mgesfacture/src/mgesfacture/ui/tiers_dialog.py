"""Dialogue de création/modification d'un tiers -- reprend le modèle de
plan_tiers de mgescompta (numero + intitule + type + compte_collectif +
classification/région/département/localité), pour permettre un
rapprochement fiable lors de l'export/import des factures vers mgescompta.
compte_collectif est en lecture seule ici : il n'est fixable/modifiable que
dans Fichier > Paramètres… (un seul compte par type de tiers, jamais tapé au
cas par cas)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mgesfacture.ui.icone import icone_ronde_verte
from mgesfacture.ui.localite_dialog import LocaliteDialog

TYPES_TIERS = ["FOURNISSEUR", "ADHERENT", "SALARIE", "AUTRE"]


def _prochain_numero(db: QSqlDatabase) -> str:
    query = QSqlQuery(db)
    query.exec("SELECT numero FROM tiers")
    max_n = 0
    while query.next():
        numero = query.value(0) or ""
        if numero.startswith("T") and numero[1:].isdigit():
            max_n = max(max_n, int(numero[1:]))
    return f"T{max_n + 1:04d}"


class TiersDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, tiers_id: int | None = None) -> None:
        super().__init__(parent)
        self.setWindowIcon(icone_ronde_verte())
        self.db = db
        self.tiers_id = tiers_id
        self.setWindowTitle("Modifier le tiers" if tiers_id else "Nouveau tiers")
        self.resize(440, 480)

        self.champ_numero = QLineEdit(self)
        self.champ_intitule = QLineEdit(self)

        self.champ_type = QComboBox(self)
        self.champ_type.addItems(TYPES_TIERS)
        self.champ_type.currentTextChanged.connect(self._appliquer_compte_collectif)

        self.champ_compte_collectif = QLineEdit(self)
        self.champ_compte_collectif.setReadOnly(True)
        self.champ_compte_collectif.setToolTip("Fixable uniquement dans Fichier > Paramètres…")

        self.champ_classification = QComboBox(self)
        self._charger_classifications()

        self.champ_region = QComboBox(self)
        self._charger_regions()

        self.champ_departement = QComboBox(self)

        self.champ_localite = QComboBox(self)
        bouton_nouvelle_localite = QPushButton("Nouvelle…", self)
        bouton_nouvelle_localite.clicked.connect(self._creer_localite)
        ligne_localite = QHBoxLayout()
        ligne_localite.addWidget(self.champ_localite, 1)
        ligne_localite.addWidget(bouton_nouvelle_localite)

        # Les 3 combos existent maintenant : sûr de câbler la cascade et de
        # faire le premier chargement (departement -> localite en cascade).
        self.champ_region.currentIndexChanged.connect(self._recharger_departements)
        self.champ_departement.currentIndexChanged.connect(self._recharger_localites)
        self._recharger_departements()

        self.champ_adresse = QLineEdit(self)
        self.champ_telephone = QLineEdit(self)
        self.champ_email = QLineEdit(self)
        self.champ_ninea = QLineEdit(self)
        self.champ_rc = QLineEdit(self)
        self.champ_actif = QCheckBox("Actif", self)
        self.champ_actif.setChecked(True)

        formulaire = QFormLayout()
        formulaire.addRow("Numéro :", self.champ_numero)
        formulaire.addRow("Intitulé :", self.champ_intitule)
        formulaire.addRow("Type :", self.champ_type)
        formulaire.addRow("Compte collectif :", self.champ_compte_collectif)
        formulaire.addRow("Classification :", self.champ_classification)
        formulaire.addRow("Région :", self.champ_region)
        formulaire.addRow("Département :", self.champ_departement)
        formulaire.addRow("Localité :", ligne_localite)
        formulaire.addRow("Adresse :", self.champ_adresse)
        formulaire.addRow("Téléphone :", self.champ_telephone)
        formulaire.addRow("Email :", self.champ_email)
        formulaire.addRow("NINEA :", self.champ_ninea)
        formulaire.addRow("RC :", self.champ_rc)
        formulaire.addRow(self.champ_actif)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        texte_bouton = "Enregistrer" if tiers_id is not None else "Créer"
        bouton_valider = boutons.addButton(texte_bouton, QDialogButtonBox.ButtonRole.AcceptRole)
        boutons.rejected.connect(self.reject)
        bouton_valider.clicked.connect(self._valider)

        layout = QVBoxLayout(self)
        layout.addLayout(formulaire)
        layout.addWidget(boutons)

        if tiers_id is not None:
            self._charger(tiers_id)
        else:
            self.champ_numero.setText(_prochain_numero(db))
            self._appliquer_compte_collectif()

    def _appliquer_compte_collectif(self) -> None:
        """Toujours la valeur courante du paramètre pour le type sélectionné
        -- jamais une saisie libre (voir Fichier > Paramètres…)."""
        query = QSqlQuery(self.db)
        query.prepare("SELECT compte_collectif FROM parametres_comptes_collectifs WHERE type = ?")
        query.addBindValue(self.champ_type.currentText())
        query.exec()
        self.champ_compte_collectif.setText(query.value(0) if query.next() else "")

    def _charger_classifications(self) -> None:
        self.champ_classification.addItem("— Aucune —", None)
        query = QSqlQuery(self.db)
        query.exec("SELECT id, abrege, libelle FROM classification ORDER BY libelle")
        while query.next():
            self.champ_classification.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _charger_regions(self) -> None:
        self.champ_region.addItem("— Aucune —", None)
        query = QSqlQuery(self.db)
        query.exec("SELECT id, code, nom FROM region ORDER BY code")
        while query.next():
            self.champ_region.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _recharger_departements(self) -> None:
        self.champ_departement.blockSignals(True)
        self.champ_departement.clear()
        self.champ_departement.addItem("— Aucun —", None)
        region_id = self.champ_region.currentData()
        if region_id is not None:
            query = QSqlQuery(self.db)
            query.prepare("SELECT id, code, nom FROM departement WHERE region_id = ? ORDER BY code")
            query.addBindValue(region_id)
            query.exec()
            while query.next():
                self.champ_departement.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))
        self.champ_departement.blockSignals(False)
        self._recharger_localites()

    def _recharger_localites(self) -> None:
        self.champ_localite.clear()
        self.champ_localite.addItem("— Aucune —", None)
        departement_id = self.champ_departement.currentData()
        if departement_id is not None:
            query = QSqlQuery(self.db)
            query.prepare("SELECT id, nom FROM localite WHERE departement_id = ? ORDER BY nom")
            query.addBindValue(departement_id)
            query.exec()
            while query.next():
                self.champ_localite.addItem(query.value(1), query.value(0))

    def _creer_localite(self) -> None:
        # Pré-rempli avec la région/département déjà sélectionnés ici, mais
        # librement modifiable dans le sous-dialogue -- la localité peut être
        # attachée à un département différent de celui affiché.
        dialog = LocaliteDialog(
            self.db, self,
            region_id=self.champ_region.currentData(),
            departement_id=self.champ_departement.currentData(),
        )
        if not dialog.exec():
            return

        index_region = self.champ_region.findData(dialog.region_id)
        if index_region >= 0:
            self.champ_region.setCurrentIndex(index_region)  # déclenche _recharger_departements (+ localites)

        index_departement = self.champ_departement.findData(dialog.departement_id)
        if index_departement >= 0:
            self.champ_departement.setCurrentIndex(index_departement)  # déclenche _recharger_localites

        index_localite = self.champ_localite.findData(dialog.localite_id)
        if index_localite >= 0:
            self.champ_localite.setCurrentIndex(index_localite)

    def _charger(self, tiers_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT numero, intitule, type, compte_collectif, classification_id, region_id, "
            "departement_id, localite_id, adresse, telephone, email, ninea, rc, actif FROM tiers WHERE id = ?"
        )
        query.addBindValue(tiers_id)
        query.exec()
        if not query.next():
            return
        self.champ_numero.setText(query.value(0))
        self.champ_intitule.setText(query.value(1))
        index_type = self.champ_type.findText(query.value(2))
        if index_type >= 0:
            self.champ_type.setCurrentIndex(index_type)
        self.champ_compte_collectif.setText(query.value(3) or "")
        index_classif = self.champ_classification.findData(query.value(4))
        if index_classif >= 0:
            self.champ_classification.setCurrentIndex(index_classif)
        index_region = self.champ_region.findData(query.value(5))
        if index_region >= 0:
            self.champ_region.setCurrentIndex(index_region)  # déclenche _recharger_departements
        index_departement = self.champ_departement.findData(query.value(6))
        if index_departement >= 0:
            self.champ_departement.setCurrentIndex(index_departement)  # déclenche _recharger_localites
        index_localite = self.champ_localite.findData(query.value(7))
        if index_localite >= 0:
            self.champ_localite.setCurrentIndex(index_localite)
        self.champ_adresse.setText(query.value(8) or "")
        self.champ_telephone.setText(query.value(9) or "")
        self.champ_email.setText(query.value(10) or "")
        self.champ_ninea.setText(query.value(11) or "")
        self.champ_rc.setText(query.value(12) or "")
        self.champ_actif.setChecked(bool(query.value(13)))

    def _valider(self) -> None:
        numero = self.champ_numero.text().strip()
        if not numero:
            QMessageBox.warning(self, "Champ manquant", "Le numéro du tiers est obligatoire.")
            return
        intitule = self.champ_intitule.text().strip()
        if not intitule:
            QMessageBox.warning(self, "Champ manquant", "L'intitulé du tiers est obligatoire.")
            return
        compte_collectif = self.champ_compte_collectif.text().strip()
        if not compte_collectif:
            QMessageBox.warning(
                self,
                "Compte collectif non configuré",
                f"Aucun compte collectif n'est défini pour le type « {self.champ_type.currentText()} ».\n"
                "Configurez-le dans Fichier > Paramètres… avant de créer ce tiers.",
            )
            return

        query = QSqlQuery(self.db)
        if self.tiers_id is None:
            query.prepare(
                "INSERT INTO tiers (numero, intitule, type, compte_collectif, classification_id, region_id, "
                "departement_id, localite_id, adresse, telephone, email, ninea, rc, actif) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
        else:
            query.prepare(
                "UPDATE tiers SET numero = ?, intitule = ?, type = ?, compte_collectif = ?, "
                "classification_id = ?, region_id = ?, departement_id = ?, localite_id = ?, "
                "adresse = ?, telephone = ?, email = ?, ninea = ?, rc = ?, actif = ? WHERE id = ?"
            )
        query.addBindValue(numero)
        query.addBindValue(intitule)
        query.addBindValue(self.champ_type.currentText())
        query.addBindValue(compte_collectif)
        query.addBindValue(self.champ_classification.currentData())
        query.addBindValue(self.champ_region.currentData())
        query.addBindValue(self.champ_departement.currentData())
        query.addBindValue(self.champ_localite.currentData())
        query.addBindValue(self.champ_adresse.text().strip() or None)
        query.addBindValue(self.champ_telephone.text().strip() or None)
        query.addBindValue(self.champ_email.text().strip() or None)
        query.addBindValue(self.champ_ninea.text().strip() or None)
        query.addBindValue(self.champ_rc.text().strip() or None)
        query.addBindValue(1 if self.champ_actif.isChecked() else 0)
        if self.tiers_id is not None:
            query.addBindValue(self.tiers_id)

        if not query.exec():
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer le tiers :\n{query.lastError().text()}")
            return

        self.accept()
