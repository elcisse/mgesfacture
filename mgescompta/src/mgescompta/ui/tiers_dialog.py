"""Dialogue de création/modification d'un tiers (adhérent, fournisseur, salarié, autre)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QCheckBox,
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
    "ADHERENT": "Adhérent",
    "FOURNISSEUR": "Fournisseur",
    "SALARIE": "Salarié",
    "AUTRE": "Autre",
}
PREFIXES_NUMERO: dict[str, str] = {"ADHERENT": "C", "FOURNISSEUR": "F", "SALARIE": "S", "AUTRE": "A"}
# Comptes collectifs conventionnels par type de tiers -- présélectionnés
# quand ils existent dans le plan comptable (même convention que
# CreerOrganisation::provisionnerTiers dans cger : 411000 pour un adhérent,
# 401100 pour un fournisseur).
COMPTES_COLLECTIFS_PAR_DEFAUT: dict[str, str] = {"ADHERENT": "411000", "FOURNISSEUR": "401100"}


class TiersDialog(QDialog):
    """tiers_id=None -> création (numéro/compte collectif suggérés) ; sinon
    -> modification du tiers existant (aucune suggestion, valeurs chargées)."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None, tiers_id: int | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.tiers_id = tiers_id
        self.setWindowTitle("Modifier le tiers" if tiers_id else "Nouveau tiers")
        self.resize(420, 380)

        self.champ_type = QComboBox(self)
        for valeur, libelle in TYPE_LABELS.items():
            self.champ_type.addItem(libelle, valeur)
        if tiers_id is None:
            self.champ_type.currentIndexChanged.connect(self._suggerer_numero)
            self.champ_type.currentIndexChanged.connect(self._suggerer_compte_collectif)

        self.champ_numero = QLineEdit(self)
        self.champ_intitule = QLineEdit(self)

        self.champ_compte_collectif = QComboBox(self)
        self._charger_comptes()

        self.champ_classification = QComboBox(self)
        self._charger_classifications()

        self.champ_region = QComboBox(self)
        self._charger_regions()
        self.champ_region.currentIndexChanged.connect(self._recharger_departements)

        self.champ_departement = QComboBox(self)
        self._recharger_departements()
        self.champ_departement.currentIndexChanged.connect(self._recharger_localites)

        self.champ_localite = QComboBox(self)
        self._recharger_localites()

        if tiers_id is None:
            # Pour un Fournisseur, le numéro suit la codification officielle
            # des prestataires (voir CODIFICATION.txt) : Classification (3
            # lettres) + Région (2 chiffres) + Département (1 lettre) +
            # Séquence (2 chiffres) -- ex. PHA13C14. Elle dépend donc aussi de
            # ces 3 champs, pas seulement du type.
            self.champ_classification.currentIndexChanged.connect(self._suggerer_numero)
            self.champ_region.currentIndexChanged.connect(self._suggerer_numero)
            self.champ_departement.currentIndexChanged.connect(self._suggerer_numero)

        self.champ_adresse = QLineEdit(self)
        self.champ_telephone = QLineEdit(self)
        self.champ_email = QLineEdit(self)
        self.champ_ninea = QLineEdit(self)
        self.champ_rc = QLineEdit(self)
        self.champ_actif = QCheckBox("Actif", self)
        self.champ_actif.setChecked(True)

        formulaire = QFormLayout()
        formulaire.addRow("Type :", self.champ_type)
        formulaire.addRow("Numéro :", self.champ_numero)
        formulaire.addRow("Intitulé :", self.champ_intitule)
        formulaire.addRow("Compte collectif :", self.champ_compte_collectif)
        formulaire.addRow("Classification :", self.champ_classification)
        formulaire.addRow("Région :", self.champ_region)
        formulaire.addRow("Département :", self.champ_departement)
        formulaire.addRow("Localité :", self.champ_localite)
        formulaire.addRow("Adresse :", self.champ_adresse)
        formulaire.addRow("Téléphone :", self.champ_telephone)
        formulaire.addRow("Email :", self.champ_email)
        formulaire.addRow("NINEA :", self.champ_ninea)
        formulaire.addRow("RC :", self.champ_rc)
        formulaire.addRow("", self.champ_actif)

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
            self._suggerer_numero()
            self._suggerer_compte_collectif()

    def _charger_comptes(self) -> None:
        query = QSqlQuery(self.db)
        query.exec("SELECT numero, intitule FROM plan_comptable ORDER BY numero")
        while query.next():
            numero, intitule = query.value(0), query.value(1)
            self.champ_compte_collectif.addItem(f"{numero} — {intitule}", numero)

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
        """Ne propose que les départements de la région sélectionnée."""
        self.champ_departement.clear()
        self.champ_departement.addItem("— Aucun —", None)
        region_id = self.champ_region.currentData()
        if region_id is None:
            return
        query = QSqlQuery(self.db)
        query.prepare("SELECT id, code, nom FROM departement WHERE region_id = ? ORDER BY code")
        query.addBindValue(region_id)
        query.exec()
        while query.next():
            self.champ_departement.addItem(f"{query.value(1)} — {query.value(2)}", query.value(0))

    def _recharger_localites(self) -> None:
        """Ne propose que les localités du département sélectionné."""
        self.champ_localite.clear()
        self.champ_localite.addItem("— Aucune —", None)
        departement_id = self.champ_departement.currentData()
        if departement_id is None:
            return
        query = QSqlQuery(self.db)
        query.prepare("SELECT id, nom FROM localite WHERE departement_id = ? ORDER BY nom")
        query.addBindValue(departement_id)
        query.exec()
        while query.next():
            self.champ_localite.addItem(query.value(1), query.value(0))

    def _charger(self, tiers_id: int) -> None:
        query = QSqlQuery(self.db)
        query.prepare(
            "SELECT numero, intitule, type, compte_collectif, classification_id, region_id, "
            "departement_id, localite_id, adresse, telephone, email, ninea, rc, actif FROM plan_tiers WHERE id = ?"
        )
        query.addBindValue(tiers_id)
        query.exec()
        if not query.next():
            return
        self.champ_type.setCurrentIndex(self.champ_type.findData(query.value(2)))
        self.champ_numero.setText(query.value(0))
        self.champ_intitule.setText(query.value(1))
        index_compte = self.champ_compte_collectif.findData(query.value(3))
        if index_compte >= 0:
            self.champ_compte_collectif.setCurrentIndex(index_compte)
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

    def _suggerer_numero(self) -> None:
        type_code = self.champ_type.currentData()

        if type_code == "FOURNISSEUR":
            abrege = self._valeur_liee("classification", "abrege", self.champ_classification.currentData())
            code_region = self._valeur_liee("region", "code", self.champ_region.currentData())
            code_departement = self._valeur_liee("departement", "code", self.champ_departement.currentData())
            if abrege and code_region and code_departement:
                self.champ_numero.setText(
                    self._prochain_numero_prestataire(abrege, code_region, code_departement)
                )
                return

        prefixe = PREFIXES_NUMERO.get(type_code, "A")
        query = QSqlQuery(self.db)
        query.prepare("SELECT numero FROM plan_tiers WHERE type = ? ORDER BY numero DESC LIMIT 1")
        query.addBindValue(type_code)
        query.exec()

        suivant = 1
        if query.next():
            chiffres = "".join(c for c in query.value(0) if c.isdigit())
            if chiffres:
                suivant = int(chiffres) + 1

        self.champ_numero.setText(f"{prefixe}{suivant:03d}")

    def _valeur_liee(self, table: str, colonne: str, id_: int | None) -> str | None:
        if id_ is None:
            return None
        query = QSqlQuery(self.db)
        query.prepare(f"SELECT {colonne} FROM {table} WHERE id = ?")
        query.addBindValue(id_)
        query.exec()
        return query.value(0) if query.next() else None

    def _prochain_numero_prestataire(self, abrege: str, code_region: str, code_departement: str) -> str:
        """Codification officielle des prestataires (voir CODIFICATION.txt) :
        Classification + Région + Département + Séquence dans ce département."""
        prefixe = f"{abrege}{code_region}{code_departement}"
        query = QSqlQuery(self.db)
        query.prepare("SELECT numero FROM plan_tiers WHERE numero LIKE ? ORDER BY numero DESC LIMIT 1")
        query.addBindValue(f"{prefixe}%")
        query.exec()

        suivant = 1
        if query.next():
            suffixe = query.value(0)[len(prefixe):]
            if suffixe.isdigit():
                suivant = int(suffixe) + 1

        return f"{prefixe}{suivant:02d}"

    def _suggerer_compte_collectif(self) -> None:
        numero_defaut = COMPTES_COLLECTIFS_PAR_DEFAUT.get(self.champ_type.currentData())
        if numero_defaut is None:
            return
        index = self.champ_compte_collectif.findData(numero_defaut)
        if index >= 0:
            self.champ_compte_collectif.setCurrentIndex(index)

    def _valider(self) -> None:
        numero = self.champ_numero.text().strip()
        intitule = self.champ_intitule.text().strip()
        if not numero or not intitule:
            QMessageBox.warning(self, "Champs manquants", "Le numéro et l'intitulé sont obligatoires.")
            return
        if self.champ_compte_collectif.count() == 0:
            QMessageBox.warning(
                self, "Plan comptable vide",
                "Activez d'abord des comptes dans le plan comptable pour choisir un compte collectif.",
            )
            return

        query = QSqlQuery(self.db)
        if self.tiers_id is None:
            query.prepare(
                "INSERT INTO plan_tiers "
                "(numero, intitule, type, compte_collectif, classification_id, region_id, departement_id, "
                "localite_id, adresse, telephone, email, ninea, rc, actif) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
        else:
            query.prepare(
                "UPDATE plan_tiers SET numero = ?, intitule = ?, type = ?, compte_collectif = ?, "
                "classification_id = ?, region_id = ?, departement_id = ?, localite_id = ?, adresse = ?, "
                "telephone = ?, email = ?, ninea = ?, rc = ?, actif = ? "
                "WHERE id = ?"
            )
        query.addBindValue(numero)
        query.addBindValue(intitule)
        query.addBindValue(self.champ_type.currentData())
        query.addBindValue(self.champ_compte_collectif.currentData())
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
