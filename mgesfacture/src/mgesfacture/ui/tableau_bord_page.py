"""Page Tableau de bord : quelques indicateurs clés, rafraîchis à chaque
fois que l'onglet est affiché."""
from __future__ import annotations

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtSql import QSqlDatabase
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mgesfacture.support.formatage import formater_montant
from mgesfacture.support.tableau_bord import calculer_indicateurs, montants_par_region, periode_disponible


def _carte(titre: str) -> tuple[QFrame, QLabel, QLabel]:
    """Un petit cadre avec un gros chiffre et une légende, dans le même
    esprit visuel qu'un widget de tableau de bord."""
    cadre = QFrame()
    cadre.setFrameShape(QFrame.Shape.StyledPanel)
    cadre.setMinimumWidth(220)

    label_valeur = QLabel("—")
    label_valeur.setStyleSheet("font-size: 22pt; font-weight: bold;")
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

        grille = QGridLayout()

        cadre_total, self.label_total, self.label_total_legende = _carte("")
        cadre_non_exp, self.label_non_exportees, _ = _carte("Non exportées")
        cadre_echeances, self.label_echeances, _ = _carte("Échéances dépassées")
        cadre_top, self.label_top, self.label_top_legende = _carte("Fournisseur principal")
        cadre_export, self.label_dernier_export, _ = _carte("Dernier export")

        grille.addWidget(cadre_total, 0, 0)
        grille.addWidget(cadre_non_exp, 0, 1)
        grille.addWidget(cadre_echeances, 0, 2)
        grille.addWidget(cadre_top, 0, 3)
        grille.addWidget(cadre_export, 0, 4)

        layout.addLayout(grille)

        # Une date/heure ne tient pas dans la même taille de police qu'un
        # montant ou un compteur -- réduite pour rester sur une ligne.
        self.label_dernier_export.setStyleSheet("font-size: 13pt; font-weight: bold;")

        layout.addWidget(QLabel("<h3>Montants enregistrés par région</h3>"))

        date_min, date_max = periode_disponible(db)
        self.champ_date_debut = QDateEdit(self)
        self.champ_date_debut.setCalendarPopup(True)
        self.champ_date_debut.setDisplayFormat("dd/MM/yyyy")
        self.champ_date_debut.setDate(
            QDate.fromString(date_min, "yyyy-MM-dd") if date_min else QDate.currentDate()
        )

        self.champ_date_fin = QDateEdit(self)
        self.champ_date_fin.setCalendarPopup(True)
        self.champ_date_fin.setDisplayFormat("dd/MM/yyyy")
        self.champ_date_fin.setDate(
            QDate.fromString(date_max, "yyyy-MM-dd") if date_max else QDate.currentDate()
        )

        bouton_filtrer = QPushButton("Filtrer", self)
        bouton_filtrer.clicked.connect(self._actualiser_tableau_region)

        barre_filtre = QHBoxLayout()
        barre_filtre.addWidget(QLabel("Du :"))
        barre_filtre.addWidget(self.champ_date_debut)
        barre_filtre.addWidget(QLabel("Au :"))
        barre_filtre.addWidget(self.champ_date_fin)
        barre_filtre.addWidget(bouton_filtrer)
        barre_filtre.addStretch(1)
        layout.addLayout(barre_filtre)

        self.table_region = QTableWidget(self)
        self.table_region.setColumnCount(2)
        self.table_region.setHorizontalHeaderLabels(["Région", "Montant enregistré"])
        self.table_region.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_region.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_region.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_region.verticalHeader().setVisible(False)
        layout.addWidget(self.table_region)

        layout.addStretch(1)

        self.refresh()

    def refresh(self) -> None:
        indicateurs = calculer_indicateurs(self.db)

        self.label_total.setText(formater_montant(indicateurs.montant_total))
        self.label_total_legende.setText(f"Total facturé ({indicateurs.nb_factures} facture(s))")

        self.label_non_exportees.setText(str(indicateurs.nb_non_exportees))
        self.label_non_exportees.parent().layout().itemAt(1).widget().setText(
            f"Non exportées ({formater_montant(indicateurs.montant_non_exportees)})"
        )

        self.label_echeances.setText(str(indicateurs.nb_echeances_depassees))
        self.label_echeances.parent().layout().itemAt(1).widget().setText(
            f"Échéances dépassées ({formater_montant(indicateurs.montant_echeances_depassees)})"
        )

        if indicateurs.top_fournisseur_nom:
            self.label_top.setText(formater_montant(indicateurs.top_fournisseur_montant))
            self.label_top_legende.setText(f"Fournisseur principal : {indicateurs.top_fournisseur_nom}")
        else:
            self.label_top.setText("—")
            self.label_top_legende.setText("Fournisseur principal")

        if indicateurs.dernier_export:
            date_export = QDateTime.fromString(indicateurs.dernier_export, "yyyy-MM-dd HH:mm:ss")
            self.label_dernier_export.setText(date_export.toString("dd/MM/yyyy HH:mm"))
        else:
            self.label_dernier_export.setText("Aucun")

        self._actualiser_tableau_region()

    def _actualiser_tableau_region(self) -> None:
        date_debut = self.champ_date_debut.date().toString("yyyy-MM-dd")
        date_fin = self.champ_date_fin.date().toString("yyyy-MM-dd")
        lignes = montants_par_region(self.db, date_debut, date_fin)

        self.table_region.setRowCount(len(lignes))
        for row, ligne in enumerate(lignes):
            self.table_region.setItem(row, 0, QTableWidgetItem(ligne["region"]))
            item_montant = QTableWidgetItem(formater_montant(ligne["montant"]))
            item_montant.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_region.setItem(row, 1, item_montant)
