"""Page Écritures comptables : liste + création/modification manuelle +
suppression contrôlée. Les opérations sont validées automatiquement dès leur
création (saisie guidée ou dialogues manuels) ; la suppression d'écritures
n'est donc plus limitée au statut « En attente », mais reste protégée par un
contrôle d'équilibre : on ne peut pas retirer une sélection qui laisserait
une opération déséquilibrée (débits ≠ crédits)."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from mgescompta.support.formatage import formater_montant
from mgescompta.ui.ecriture_dialog import EcritureDialog
from mgescompta.ui.listable_page import ListablePage

COLONNES = {
    "id": "ID",
    "operation_id": "Opération",
    "date": "Date",
    "libelle": "Libellé",
    "compte": "Compte",
    "montant": "Montant",
    "sens": "Sens",
    "statut": "Statut",
}


class EcrituresPage(ListablePage):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(
            db, "ecritures_comptables", "Écritures comptables", COLONNES,
            EcritureDialog, "Nouvelle écriture…",
            edit_dialog_factory=EcritureDialog,
            permettre_suppression=False,  # bouton remplacé ci-dessous par la version équilibrée
            colonnes_montant={"montant"},
            parent=parent,
        )

        bouton_supprimer = QPushButton("Supprimer la sélection", self)
        bouton_supprimer.clicked.connect(self._supprimer_selection_equilibree)
        self.entete_layout.addWidget(bouton_supprimer)

    def _supprimer_selection_equilibree(self) -> None:
        lignes = self.liste.view.selectionModel().selectedRows()
        if not lignes:
            QMessageBox.information(self, "Aucune sélection", "Sélectionnez au moins une écriture à supprimer.")
            return

        colonne_id = self.liste.model.fieldIndex("id")
        ids_a_supprimer = {
            self.liste.model.data(self.liste.model.index(index.row(), colonne_id)) for index in lignes
        }

        erreur = self._verifier_equilibre_apres_suppression(ids_a_supprimer)
        if erreur:
            QMessageBox.warning(self, "Suppression impossible", erreur)
            return

        reponse = QMessageBox.question(
            self,
            "Supprimer les écritures",
            f"Supprimer {len(ids_a_supprimer)} écriture(s) sélectionnée(s) ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reponse != QMessageBox.StandardButton.Yes:
            return

        self.db.transaction()
        delete_query = QSqlQuery(self.db)
        delete_query.prepare("DELETE FROM ecritures_comptables WHERE id = ?")
        for ecriture_id in ids_a_supprimer:
            delete_query.addBindValue(ecriture_id)
            if not delete_query.exec():
                self.db.rollback()
                QMessageBox.critical(self, "Erreur", f"Échec de la suppression :\n{delete_query.lastError().text()}")
                self.liste.refresh()
                return

        # Nettoie les opérations devenues sans aucune écriture (suppression complète).
        delete_operations_vides = QSqlQuery(self.db)
        delete_operations_vides.exec(
            "DELETE FROM operations_comptables WHERE id NOT IN (SELECT DISTINCT operation_id FROM ecritures_comptables)"
        )

        self.db.commit()
        self.liste.refresh()
        QMessageBox.information(self, "Supprimé", f"{len(ids_a_supprimer)} écriture(s) supprimée(s).")

    def _verifier_equilibre_apres_suppression(self, ids_a_supprimer: set[int]) -> str | None:
        """Pour chaque opération touchée, vérifie que les écritures restantes
        (celles non sélectionnées) resteraient équilibrées (débits = crédits,
        comparaison en centimes pour éviter les erreurs d'arrondi)."""
        placeholders = ",".join("?" for _ in ids_a_supprimer)
        operations_query = QSqlQuery(self.db)
        operations_query.prepare(
            f"SELECT DISTINCT operation_id FROM ecritures_comptables WHERE id IN ({placeholders})"
        )
        for ecriture_id in ids_a_supprimer:
            operations_query.addBindValue(ecriture_id)
        operations_query.exec()
        operations_affectees = []
        while operations_query.next():
            operations_affectees.append(operations_query.value(0))

        lignes_query = QSqlQuery(self.db)
        for operation_id in operations_affectees:
            lignes_query.prepare("SELECT id, montant, sens FROM ecritures_comptables WHERE operation_id = ?")
            lignes_query.addBindValue(operation_id)
            lignes_query.exec()

            solde_centimes = 0
            while lignes_query.next():
                ecriture_id, montant, sens = lignes_query.value(0), lignes_query.value(1), lignes_query.value(2)
                if ecriture_id in ids_a_supprimer:
                    continue  # retirée de la sélection : ne compte pas dans le solde restant
                centimes = round(montant * 100)
                solde_centimes += centimes if sens == "DEBIT" else -centimes

            if solde_centimes != 0:
                libelle_query = QSqlQuery(self.db)
                libelle_query.prepare("SELECT libelle FROM operations_comptables WHERE id = ?")
                libelle_query.addBindValue(operation_id)
                libelle_query.exec()
                libelle = libelle_query.value(0) if libelle_query.next() else operation_id
                ecart = abs(solde_centimes) / 100
                sens_ecart = "débit" if solde_centimes > 0 else "crédit"
                return (
                    f"Cette suppression laisserait l'opération « {libelle} » déséquilibrée "
                    f"(écart de {formater_montant(ecart)} au {sens_ecart}).\n\n"
                    "Sélectionnez aussi les écritures correspondantes de cette opération, "
                    "ou supprimez l'opération entière depuis Opérations comptables."
                )

        return None
