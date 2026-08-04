"""Fenêtre principale : appli autonome et volontairement simple -- trois
onglets (Tableau de bord, Factures, Tiers), pas de comptabilité, pas de MDI."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtSql import QSqlDatabase
from PySide6.QtWidgets import QMainWindow, QStatusBar, QTabWidget

from mgesfacture.ui.factures_page import FacturesPage
from mgesfacture.ui.icone import icone_ronde_verte
from mgesfacture.ui.parametres_dialog import ParametresDialog
from mgesfacture.ui.tableau_bord_page import TableauBordPage
from mgesfacture.ui.tiers_page import TiersPage


class MainWindow(QMainWindow):
    def __init__(self, db: QSqlDatabase) -> None:
        super().__init__()
        self.db = db
        self.setWindowTitle("MgesFacture")
        self.setWindowIcon(icone_ronde_verte())
        self.resize(1000, 650)

        self.onglets = QTabWidget(self)
        self.page_tableau_bord = TableauBordPage(db)
        self.page_factures = FacturesPage(db)
        self.page_tiers = TiersPage(db)
        self.onglets.addTab(self.page_tableau_bord, "Tableau de bord")
        self.onglets.addTab(self.page_factures, "Factures")
        self.onglets.addTab(self.page_tiers, "Tiers")
        self.setCentralWidget(self.onglets)

        self.setStatusBar(QStatusBar(self))

        menu_fichier = self.menuBar().addMenu("&Fichier")
        self.action_parametres = QAction("&Paramètres…", self)
        self.action_parametres.triggered.connect(self._ouvrir_parametres)
        menu_fichier.addAction(self.action_parametres)

        # Un tiers créé depuis l'onglet Tiers doit apparaître immédiatement
        # dans le sélecteur de la prochaine facture créée -- FactureDialog
        # recharge sa liste à chaque ouverture, donc rien de plus à faire ici
        # qu'un rafraîchissement de la liste au retour.
        self.onglets.currentChanged.connect(self._sur_changement_onglet)

    def _sur_changement_onglet(self, index: int) -> None:
        widget = self.onglets.widget(index)
        if widget is self.page_factures:
            self.page_factures.refresh()
        elif widget is self.page_tableau_bord:
            self.page_tableau_bord.refresh()

    def _ouvrir_parametres(self) -> None:
        if ParametresDialog(self.db, self).exec():
            self.page_tiers.refresh()
            self.page_tableau_bord.refresh()
