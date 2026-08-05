"""Page Tableau de bord : trésorerie, factures fournisseurs à régler,
répartition des charges santé/fonctionnement, opérations en attente de
validation -- rafraîchis à la demande (bouton, ou Actualiser du menu)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlDatabase
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mgescompta.support.formatage import formater_montant
from mgescompta.support.tableau_bord import calculer_indicateurs


def _carte(titre: str) -> tuple[QFrame, QLabel, QLabel]:
    """Un petit cadre avec un gros chiffre et une légende."""
    cadre = QFrame()
    cadre.setFrameShape(QFrame.Shape.StyledPanel)
    cadre.setMinimumWidth(200)

    label_valeur = QLabel("—")
    label_valeur.setStyleSheet("font-size: 20pt; font-weight: bold;")
    label_valeur.setAlignment(Qt.AlignmentFlag.AlignCenter)

    label_legende = QLabel(titre)
    label_legende.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label_legende.setWordWrap(True)

    layout = QVBoxLayout(cadre)
    layout.addWidget(label_valeur)
    layout.addWidget(label_legende)

    return cadre, label_valeur, label_legende


class TableauBordPage(QWidget):
    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Tableau de bord</h2>"))

        bouton_actualiser = QPushButton("Actualiser", self)
        bouton_actualiser.clicked.connect(self.refresh)
        layout.addWidget(bouton_actualiser, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(QLabel("<h3>Trésorerie</h3>"))
        grille_tresorerie = QGridLayout()
        cadre_caisse, self.label_caisse, _ = _carte("Solde Caisse")
        cadre_banque, self.label_banque, _ = _carte("Solde Banque")
        grille_tresorerie.addWidget(cadre_caisse, 0, 0)
        grille_tresorerie.addWidget(cadre_banque, 0, 1)
        layout.addLayout(grille_tresorerie)

        layout.addWidget(QLabel("<h3>Factures fournisseurs</h3>"))
        grille_factures = QGridLayout()
        cadre_a_regler, self.label_a_regler, self.label_a_regler_legende = _carte("Factures à régler")
        cadre_operations, self.label_operations, self.label_operations_legende = _carte(
            "Opérations en attente de validation"
        )
        grille_factures.addWidget(cadre_a_regler, 0, 0)
        grille_factures.addWidget(cadre_operations, 0, 1)
        layout.addLayout(grille_factures)

        layout.addWidget(QLabel("<h3>Répartition des charges</h3>"))
        grille_charges = QGridLayout()
        cadre_sante, self.label_sante, _ = _carte("Santé (652000)")
        cadre_fonctionnement, self.label_fonctionnement, _ = _carte("Fonctionnement (autres comptes)")
        grille_charges.addWidget(cadre_sante, 0, 0)
        grille_charges.addWidget(cadre_fonctionnement, 0, 1)
        layout.addLayout(grille_charges)

        layout.addStretch(1)

        self.refresh()

    def refresh(self) -> None:
        indicateurs = calculer_indicateurs(self.db)

        self.label_caisse.setText(formater_montant(indicateurs.solde_caisse))
        self.label_banque.setText(formater_montant(indicateurs.solde_banque))

        self.label_a_regler.setText(formater_montant(indicateurs.montant_factures_a_regler))
        if indicateurs.nb_echeances_depassees:
            self.label_a_regler_legende.setText(
                f"Factures à régler ({indicateurs.nb_factures_a_regler}) — "
                f"dont {indicateurs.nb_echeances_depassees} en retard "
                f"({formater_montant(indicateurs.montant_echeances_depassees)})"
            )
        else:
            self.label_a_regler_legende.setText(f"Factures à régler ({indicateurs.nb_factures_a_regler})")

        self.label_operations.setText(str(indicateurs.nb_operations_en_attente))
        self.label_operations_legende.setText(
            f"Opérations en attente de validation "
            f"({formater_montant(indicateurs.montant_operations_en_attente)})"
        )

        self.label_sante.setText(formater_montant(indicateurs.montant_charges_sante))
        self.label_fonctionnement.setText(formater_montant(indicateurs.montant_charges_fonctionnement))
