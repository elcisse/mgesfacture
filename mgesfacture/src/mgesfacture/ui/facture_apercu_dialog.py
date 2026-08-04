"""Dialogue en lecture seule : aperçu complet d'une facture."""
from __future__ import annotations

from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from mgesfacture.support.formatage import formater_montant
from mgesfacture.ui.icone import icone_ronde_verte


class FactureApercuDialog(QDialog):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None, facture_id: int) -> None:
        super().__init__(parent)
        self.setWindowIcon(icone_ronde_verte())
        self.setWindowTitle("Aperçu de la facture")
        self.resize(440, 320)

        layout = QVBoxLayout(self)

        entete = QSqlQuery(db)
        entete.prepare(
            "SELECT f.numero_facture, f.date_facture, f.annee_mois, f.date_echeance, f.libelle, f.montant, "
            "t.intitule, t.telephone, t.email, f.reference_interne "
            "FROM factures f JOIN tiers t ON t.id = f.tiers_id WHERE f.id = ?"
        )
        entete.addBindValue(facture_id)
        entete.exec()
        if not entete.next():
            layout.addWidget(QLabel("Cette facture n'existe plus."))
            boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            boutons.rejected.connect(self.reject)
            layout.addWidget(boutons)
            return

        (numero, date_facture, annee_mois, date_echeance, libelle, montant,
         fournisseur, telephone, email, reference_interne) = (entete.value(i) for i in range(10))

        formulaire = QFormLayout()
        formulaire.addRow("Fournisseur :", QLabel(fournisseur))
        formulaire.addRow("Téléphone :", QLabel(telephone or "—"))
        formulaire.addRow("Email :", QLabel(email or "—"))
        formulaire.addRow("Référence interne :", QLabel(reference_interne or "—"))
        formulaire.addRow("N° de facture :", QLabel(numero))
        formulaire.addRow("Date de la facture :", QLabel(date_facture))
        formulaire.addRow("Année-mois :", QLabel(annee_mois))
        formulaire.addRow("Échéance :", QLabel(date_echeance or "—"))
        formulaire.addRow("Libellé :", QLabel(libelle or "—"))
        formulaire.addRow("Montant :", QLabel(formater_montant(montant)))
        layout.addLayout(formulaire)

        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        boutons.rejected.connect(self.reject)
        layout.addWidget(boutons)
