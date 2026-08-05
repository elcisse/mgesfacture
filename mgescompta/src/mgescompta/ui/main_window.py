"""Fenêtre principale, style Sage i7 : panneau de navigation à icônes par
catégorie, zone de travail MDI (fenêtres internes), barre d'outils et barre
d'état dossier/exercice/utilisateur."""
from __future__ import annotations

import getpass
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QMessageBox,
    QStyle,
    QToolBox,
    QWidget,
)

from mgescompta import __version__
from mgescompta.db.database import DB_PATH
from mgescompta.support.mise_a_jour import verifier_mise_a_jour
from mgescompta.ui.classification_page import ClassificationPage
from mgescompta.ui.departement_dialog import DepartementDialog
from mgescompta.ui.ecritures_page import EcrituresPage
from mgescompta.ui.exercice_dialog import ExerciceDialog
from mgescompta.ui.factures_page import FacturesPage
from mgescompta.ui.journal_dialog import JournalDialog
from mgescompta.ui.listable_page import ListablePage
from mgescompta.ui.localite_dialog import LocaliteDialog
from mgescompta.ui.modele_saisie_dialog import ModeleSaisieDialog
from mgescompta.ui.nouvelle_saisie_page import NouvelleSaisiePage
from mgescompta.ui.operation_dialog import OperationDialog
from mgescompta.ui.operations_page import OperationsPage
from mgescompta.ui.plan_comptable_edit_dialog import PlanComptableEditDialog
from mgescompta.ui.region_dialog import RegionDialog
from mgescompta.ui.selection_comptes_dialog import SelectionComptesDialog
from mgescompta.ui.table_page import SqlTablePage
from mgescompta.ui.tiers_dialog import TiersDialog
from mgescompta.ui.tiers_page import TiersPage

DOSSIER_NOM = "MgesCompta"


@dataclass(frozen=True)
class ModuleDef:
    id: str
    titre: str
    categorie: str
    icone: QStyle.StandardPixmap
    fabrique: Callable[[QSqlDatabase], QWidget]


def _colonnes_page(table: str, titre: str, colonnes: dict[str, str]) -> Callable[[QSqlDatabase], QWidget]:
    return lambda db: SqlTablePage(db, table, titre, colonnes)


def _listable_page(
    table: str,
    titre: str,
    colonnes: dict[str, str],
    dialog_factory,
    bouton_texte: str = "Ajouter…",
    edit_dialog_factory=None,
    permettre_suppression: bool = False,
    garde_modification=None,
    garde_suppression=None,
    relations: dict[str, tuple[str, str]] | None = None,
    tri: str | None = None,
) -> Callable[[QSqlDatabase], QWidget]:
    return lambda db: ListablePage(
        db, table, titre, colonnes, dialog_factory, bouton_texte,
        edit_dialog_factory=edit_dialog_factory,
        permettre_suppression=permettre_suppression,
        garde_modification=garde_modification,
        garde_suppression=garde_suppression,
        relations=relations,
        tri=tri,
    )


MODULE_DEFS: list[ModuleDef] = [
    ModuleDef(
        "plan_comptable",
        "Plan comptable",
        "Structure",
        QStyle.StandardPixmap.SP_FileDialogListView,
        _listable_page(
            "plan_comptable", "Plan comptable",
            {
                "id": "ID",
                "numero": "Numéro",
                "intitule": "Intitulé",
                "nature": "Nature",
                "report_a_nouveau": "Report à nouveau",
                "actif": "Actif",
            },
            SelectionComptesDialog,
            "Ajouter des comptes depuis le référentiel…",
            edit_dialog_factory=PlanComptableEditDialog,
            tri="numero",
        ),
    ),
    ModuleDef(
        "journaux",
        "Journaux",
        "Structure",
        QStyle.StandardPixmap.SP_FileDialogDetailedView,
        _listable_page(
            "code_journaux", "Journaux",
            {"id": "ID", "type": "Type", "code": "Code", "intitule": "Intitulé"},
            JournalDialog,
            "Nouveau journal…",
            edit_dialog_factory=JournalDialog,
            permettre_suppression=True,
        ),
    ),
    ModuleDef(
        "exercices",
        "Exercices comptables",
        "Structure",
        QStyle.StandardPixmap.SP_FileDialogInfoView,
        _listable_page(
            "exercices_comptables", "Exercices comptables",
            {"id": "ID", "libelle": "Libellé", "date_debut": "Début", "date_fin": "Fin", "statut": "Statut"},
            ExerciceDialog,
            "Nouvel exercice…",
            edit_dialog_factory=ExerciceDialog,
            permettre_suppression=True,
        ),
    ),
    ModuleDef(
        "tiers",
        "Tiers",
        "Tiers",
        QStyle.StandardPixmap.SP_DirIcon,
        lambda db: TiersPage(db),
    ),
    ModuleDef(
        "nouvelle_saisie",
        "Nouvelle saisie",
        "Saisie",
        QStyle.StandardPixmap.SP_DialogYesButton,
        lambda db: NouvelleSaisiePage(db),
    ),
    ModuleDef(
        "modeles_saisie",
        "Modèles de saisie",
        "Saisie",
        QStyle.StandardPixmap.SP_FileDialogNewFolder,
        _listable_page(
            "modeles_saisie", "Modèles de saisie",
            {
                "id": "ID",
                "code": "Code",
                "nom": "Nom",
                "journal_type": "Journal",
                "actif": "Actif",
                "ordre_affichage": "Ordre",
            },
            ModeleSaisieDialog,
            "Nouveau modèle…",
            edit_dialog_factory=ModeleSaisieDialog,
            permettre_suppression=True,
        ),
    ),
    ModuleDef(
        "factures",
        "Factures",
        "Saisie",
        QStyle.StandardPixmap.SP_FileDialogDetailedView,
        lambda db: FacturesPage(db),
    ),
    ModuleDef(
        "operations",
        "Opérations comptables (avancé)",
        "Saisie",
        QStyle.StandardPixmap.SP_ArrowRight,
        lambda db: OperationsPage(db),
    ),
    ModuleDef(
        "ecritures",
        "Écritures comptables (avancé)",
        "Saisie",
        QStyle.StandardPixmap.SP_FileDialogContentsView,
        lambda db: EcrituresPage(db),
    ),
    ModuleDef(
        "liste_comptes",
        "Liste des comptes",
        "Référentiels",
        QStyle.StandardPixmap.SP_DriveHDIcon,
        _colonnes_page(
            "liste_des_comptes", "Liste des comptes",
            {"id": "ID", "code": "Code", "libelle": "Libellé", "classe": "Classe", "parent_code": "Parent"},
        ),
    ),
    ModuleDef(
        "liste_journaux",
        "Liste des journaux",
        "Référentiels",
        QStyle.StandardPixmap.SP_DriveNetIcon,
        _colonnes_page(
            "liste_des_journaux", "Liste des journaux",
            {"id": "ID", "type": "Type", "code": "Code", "intitule": "Intitulé", "ordre_affichage": "Ordre"},
        ),
    ),
    ModuleDef(
        "classification",
        "Classification",
        "Référentiels",
        QStyle.StandardPixmap.SP_FileDialogInfoView,
        lambda db: ClassificationPage(db),
    ),
    ModuleDef(
        "regions",
        "Régions",
        "Référentiels",
        QStyle.StandardPixmap.SP_DirIcon,
        _listable_page(
            "region", "Régions",
            {"id": "ID", "code": "Code", "nom": "Nom"},
            RegionDialog,
            "Nouvelle région…",
            edit_dialog_factory=RegionDialog,
            permettre_suppression=True,
        ),
    ),
    ModuleDef(
        "departements",
        "Départements",
        "Référentiels",
        QStyle.StandardPixmap.SP_DirOpenIcon,
        _listable_page(
            "departement", "Départements",
            {"id": "ID", "region_id": "Région", "code": "Code", "nom": "Nom"},
            DepartementDialog,
            "Nouveau département…",
            edit_dialog_factory=DepartementDialog,
            permettre_suppression=True,
        ),
    ),
    ModuleDef(
        "localites",
        "Localités",
        "Référentiels",
        QStyle.StandardPixmap.SP_FileDialogInfoView,
        _listable_page(
            "localite", "Localités",
            {"id": "ID", "departement_id": "Département", "nom": "Nom"},
            LocaliteDialog,
            "Nouvelle localité…",
            edit_dialog_factory=LocaliteDialog,
            permettre_suppression=True,
        ),
    ),
]

CATEGORIES_ORDRE = ["Structure", "Tiers", "Saisie", "Référentiels"]

# Modules mis en avant dans la barre d'outils, comme les raccourcis de Sage.
MODULES_BARRE_OUTILS = ["nouvelle_saisie", "plan_comptable", "tiers", "factures", "operations"]


class MainWindow(QMainWindow):
    def __init__(self, db: QSqlDatabase) -> None:
        super().__init__()
        self.db = db
        self.setWindowTitle("MgesCompta")
        self.resize(1200, 750)

        self._modules: dict[str, ModuleDef] = {m.id: m for m in MODULE_DEFS}
        self._sous_fenetres: dict[str, QMdiSubWindow] = {}

        self.mdi = QMdiArea(self)
        self.mdi.setViewMode(QMdiArea.ViewMode.SubWindowView)
        self.setCentralWidget(self.mdi)

        self._build_actions()
        self._build_menu_bar()
        self._build_toolbar()
        self._build_navigation_dock()
        self._build_status_bar()

        self.ouvrir_module("nouvelle_saisie")

    # -- Navigation -----------------------------------------------------

    def _build_navigation_dock(self) -> None:
        toolbox = QToolBox(self)
        toolbox.setMinimumWidth(220)

        for categorie in CATEGORIES_ORDRE:
            liste = QListWidget(toolbox)
            liste.setViewMode(QListWidget.ViewMode.IconMode)
            liste.setIconSize(QSize(32, 32))
            liste.setGridSize(QSize(96, 84))
            liste.setMovement(QListWidget.Movement.Static)
            liste.setResizeMode(QListWidget.ResizeMode.Adjust)
            liste.setWrapping(True)
            liste.setSpacing(4)
            liste.setFlow(QListWidget.Flow.LeftToRight)

            for module in MODULE_DEFS:
                if module.categorie != categorie:
                    continue
                item = QListWidgetItem(self.style().standardIcon(module.icone), module.titre)
                item.setData(Qt.ItemDataRole.UserRole, module.id)
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                liste.addItem(item)

            liste.itemClicked.connect(lambda item: self.ouvrir_module(item.data(Qt.ItemDataRole.UserRole)))
            toolbox.addItem(liste, categorie)

        dock = QDockWidget("Navigation", self)
        dock.setObjectName("dock_navigation")
        dock.setWidget(toolbox)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def ouvrir_module(self, module_id: str) -> None:
        sous_fenetre = self._sous_fenetres.get(module_id)
        if sous_fenetre is not None:
            try:
                sous_fenetre.show()
                sous_fenetre.showNormal()
                # Fermer une sous-fenêtre (clic sur X) masque aussi son
                # widget interne ; le réafficher ne suffit pas à le
                # remontrer automatiquement -- sans cette ligne, la
                # sous-fenêtre réapparaît vide.
                sous_fenetre.widget().show()
                self.mdi.setActiveSubWindow(sous_fenetre)
                return
            except RuntimeError:
                pass  # la fenêtre C++ a été détruite entre-temps : on la recrée

        module = self._modules[module_id]
        contenu = module.fabrique(self.db)
        sous_fenetre = self.mdi.addSubWindow(contenu)
        sous_fenetre.setWindowTitle(module.titre)
        sous_fenetre.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        sous_fenetre.resize(720, 460)
        sous_fenetre.show()
        self.mdi.setActiveSubWindow(sous_fenetre)
        self._sous_fenetres[module_id] = sous_fenetre

    # -- Actions / menu / barre d'outils ---------------------------------

    def _build_actions(self) -> None:
        style = self.style()

        self.action_refresh = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "&Actualiser", self)
        self.action_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        self.action_refresh.triggered.connect(self._refresh_current_page)

        self.action_quit = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton), "&Quitter", self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.triggered.connect(self._quitter_avec_confirmation)

        self.action_nouvel_exercice = QAction(
            style.standardIcon(self._modules["exercices"].icone), "&Nouvel exercice…", self
        )
        self.action_nouvel_exercice.triggered.connect(self._ouvrir_nouvel_exercice)

        self.action_parametres_societe = self._action_a_venir("&Paramètres de société…")
        self.action_post_budgetaire = self._action_a_venir("Post budgétaire")
        self.action_abonnement = self._action_a_venir("Abonnement")
        self.action_ecriture_abonnement = self._action_a_venir("Écriture d'abonnement")
        self.action_fin_exercice = self._action_a_venir("Fin d'exercice")

        # Libellés spécifiques au menu (distincts des titres de navigation),
        # branchés sur les mêmes écrans -- aucune nouvelle fenêtre créée.
        self.action_plan_comptable_menu = self._action_module("plan_comptable", "Plan comptable")
        self.action_plan_tiers_menu = self._action_module("tiers", "Plan tiers")
        self.action_classification_menu = self._action_module("classification", "Classification")
        self.action_code_journaux_menu = self._action_module("journaux", "Code journaux")
        self.action_modeles_menu = self._action_module("modeles_saisie", "Modèles")
        self.action_regions_menu = self._action_module("regions", "Régions")
        self.action_departements_menu = self._action_module("departements", "Départements")
        self.action_localites_menu = self._action_module("localites", "Localités")
        self.action_saisie_ecriture_menu = self._action_module("operations", "Saisie écriture")
        self.action_saisie_par_modele_menu = self._action_module("nouvelle_saisie", "Saisie par modèle")
        self.action_factures_menu = self._action_module("factures", "Factures")

        self.action_cascade = QAction("&Cascade", self)
        self.action_cascade.triggered.connect(self.mdi.cascadeSubWindows)

        self.action_mosaique = QAction("&Mosaïque", self)
        self.action_mosaique.triggered.connect(self.mdi.tileSubWindows)

        self.action_fermer_tout = QAction("Fermer &tout", self)
        self.action_fermer_tout.triggered.connect(self._fermer_tout)

        self.action_verifier_maj = QAction("Vérifier les mises à jour…", self)
        self.action_verifier_maj.triggered.connect(self._verifier_mise_a_jour)

        self.action_about = QAction("À propos de MgesCompta", self)
        self.action_about.triggered.connect(self._show_about)

        self.actions_modules: dict[str, QAction] = {}
        for module in MODULE_DEFS:
            action = QAction(style.standardIcon(module.icone), module.titre, self)
            action.triggered.connect(lambda checked=False, mid=module.id: self.ouvrir_module(mid))
            self.actions_modules[module.id] = action

    def _action_module(self, module_id: str, texte: str) -> QAction:
        """Action de menu qui ouvre un écran déjà existant (voir
        ouvrir_module) sous un libellé de menu propre, sans dupliquer la fenêtre."""
        action = QAction(self.style().standardIcon(self._modules[module_id].icone), texte, self)
        action.triggered.connect(lambda checked=False, mid=module_id: self.ouvrir_module(mid))
        return action

    def _action_a_venir(self, texte: str) -> QAction:
        """Entrée de menu prévue dans la structure mais dont l'écran n'existe
        pas encore -- affichée mais désactivée plutôt que de créer une fenêtre vide."""
        action = QAction(texte, self)
        action.setEnabled(False)
        action.setToolTip("Écran pas encore disponible")
        action.setStatusTip("Écran pas encore disponible")
        return action

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        menu_fichier = menu_bar.addMenu("&Fichier")
        menu_fichier.addAction(self.action_nouvel_exercice)
        menu_fichier.addAction(self.action_parametres_societe)
        menu_fichier.addSeparator()
        menu_fichier.addAction(self.action_quit)

        menu_structure = menu_bar.addMenu("&Structure")
        menu_structure.addAction(self.action_plan_comptable_menu)
        menu_structure.addAction(self.action_plan_tiers_menu)
        menu_structure.addAction(self.action_classification_menu)
        menu_structure.addAction(self.action_code_journaux_menu)
        menu_structure.addAction(self.action_post_budgetaire)
        menu_structure.addAction(self.action_modeles_menu)
        menu_structure.addAction(self.action_abonnement)

        sous_menu_localisation = menu_structure.addMenu("Régions et départements")
        sous_menu_localisation.addAction(self.action_regions_menu)
        sous_menu_localisation.addAction(self.action_departements_menu)
        sous_menu_localisation.addAction(self.action_localites_menu)

        menu_traitement = menu_bar.addMenu("&Traitement")
        menu_traitement.addAction(self.action_saisie_ecriture_menu)
        menu_traitement.addAction(self.action_saisie_par_modele_menu)
        menu_traitement.addAction(self.action_factures_menu)
        menu_traitement.addAction(self.action_ecriture_abonnement)
        menu_traitement.addAction(self.action_fin_exercice)

        menu_fenetre = menu_bar.addMenu("Fe&nêtre")
        menu_fenetre.addAction(self.action_cascade)
        menu_fenetre.addAction(self.action_mosaique)
        menu_fenetre.addSeparator()
        menu_fenetre.addAction(self.action_fermer_tout)

        menu_aide = menu_bar.addMenu("&Aide")
        menu_aide.addAction(self.action_verifier_maj)
        menu_aide.addSeparator()
        menu_aide.addAction(self.action_about)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Principal")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(32, 32))

        for module_id in MODULES_BARRE_OUTILS:
            toolbar.addAction(self.actions_modules[module_id])
        toolbar.addSeparator()
        toolbar.addAction(self.action_refresh)
        toolbar.addSeparator()
        toolbar.addAction(self.action_quit)

    def _fermer_tout(self) -> None:
        # WA_DeleteOnClose est désactivé sur chaque sous-fenêtre (voir
        # ouvrir_module) : fermer masque sans détruire, donc _sous_fenetres
        # reste valide pour une réouverture ultérieure sans doublon.
        self.mdi.closeAllSubWindows()

    def _ouvrir_nouvel_exercice(self) -> None:
        dialog = ExerciceDialog(self.db, self)
        if not dialog.exec():
            return
        sous_fenetre = self._sous_fenetres.get("exercices")
        if sous_fenetre is not None:
            try:
                sous_fenetre.widget().refresh()
            except RuntimeError:
                pass  # la fenêtre C++ a été détruite entre-temps
        self._refresh_status_bar()

    def _quitter_avec_confirmation(self) -> None:
        reponse = QMessageBox.question(
            self,
            "Quitter MgesCompta",
            "Voulez-vous vraiment quitter l'application ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reponse == QMessageBox.StandardButton.Yes:
            self.close()

    def _refresh_current_page(self) -> None:
        sous_fenetre = self.mdi.activeSubWindow()
        if sous_fenetre is None:
            return
        contenu = sous_fenetre.widget()
        if isinstance(contenu, (SqlTablePage, ListablePage, NouvelleSaisiePage, ClassificationPage)):
            contenu.refresh()
        self._refresh_status_bar()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "À propos de MgesCompta",
            f"MgesCompta v{__version__}\nApplication de gestion de comptabilité (PySide6 + SQLite).",
        )

    def _verifier_mise_a_jour(self) -> None:
        resultat = verifier_mise_a_jour()
        if resultat.erreur:
            QMessageBox.warning(
                self,
                "Vérification impossible",
                f"Impossible de vérifier les mises à jour (pas de connexion ?) :\n{resultat.erreur}",
            )
            return
        if resultat.a_jour:
            QMessageBox.information(
                self, "À jour", f"Vous utilisez la dernière version (v{resultat.version_locale})."
            )
            return
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Icon.Information)
        boite.setWindowTitle("Nouvelle version disponible")
        boite.setText(
            f"Version installée : v{resultat.version_locale}\n"
            f"Nouvelle version disponible : v{resultat.version_distante}"
        )
        bouton_ouvrir = boite.addButton("Ouvrir la page de téléchargement…", QMessageBox.ButtonRole.ActionRole)
        boite.addButton(QMessageBox.StandardButton.Close)
        boite.exec()
        if boite.clickedButton() is bouton_ouvrir and resultat.url_release:
            QDesktopServices.openUrl(QUrl(resultat.url_release))

    # -- Barre d'état -----------------------------------------------------

    def _build_status_bar(self) -> None:
        barre = self.statusBar()

        self.label_dossier = QLabel(f"Dossier : {DOSSIER_NOM}")
        self.label_exercice = QLabel()
        self.label_utilisateur = QLabel(f"Utilisateur : {getpass.getuser()}")
        self.label_base = QLabel(f"Base : {DB_PATH}")

        for label in (self.label_dossier, self.label_exercice, self.label_utilisateur):
            barre.addPermanentWidget(label)
            separateur = QFrame(self)
            separateur.setFrameShape(QFrame.Shape.VLine)
            barre.addPermanentWidget(separateur)

        barre.addWidget(self.label_base)

        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        query = QSqlQuery(self.db)
        query.exec(
            "SELECT libelle, date_debut, date_fin FROM exercices_comptables "
            "WHERE statut = 'OUVERT' ORDER BY date_debut DESC LIMIT 1"
        )
        if query.next():
            libelle, debut, fin = query.value(0), query.value(1), query.value(2)
            self.label_exercice.setText(f"Exercice : {libelle} ({debut} → {fin})")
        else:
            self.label_exercice.setText("Exercice : aucun exercice ouvert")
