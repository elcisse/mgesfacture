"""Dialogue de sélection de comptes du référentiel pour activation dans le
plan comptable de l'entreprise."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mgescompta.support.plan_comptable import (
    NATURE_LABELS,
    NATURE_PAR_DEFAUT_SELON_CLASSE,
    REPORT_A_NOUVEAU_LABELS,
    report_a_nouveau_par_defaut,
)

COL_CASE, COL_CODE, COL_LIBELLE, COL_CLASSE, COL_NATURE, COL_REPORT = range(6)


class SelectionComptesDialog(QDialog):
    """Permet de choisir, parmi les comptes feuilles du référentiel SYCEBNL
    pas encore activés, lesquels ajouter au plan comptable -- avec nature et
    règle de report à nouveau pré-remplies selon la classe (modifiables)."""

    def __init__(self, db: QSqlDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Ajouter des comptes au plan comptable")
        self.resize(900, 600)

        self.recherche = QLineEdit(self)
        self.recherche.setPlaceholderText("Rechercher par code ou libellé…")
        self.recherche.textChanged.connect(self._appliquer_filtre)

        self.filtre_classe = QComboBox(self)
        self.filtre_classe.addItem("Toutes les classes", None)
        for classe in range(1, 10):
            self.filtre_classe.addItem(f"Classe {classe}", classe)
        self.filtre_classe.currentIndexChanged.connect(self._appliquer_filtre)

        barre_filtre = QHBoxLayout()
        barre_filtre.addWidget(QLabel("Recherche :"))
        barre_filtre.addWidget(self.recherche, stretch=1)
        barre_filtre.addWidget(self.filtre_classe)

        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["", "Code", "Libellé", "Classe", "Nature", "Report à nouveau"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_LIBELLE, QHeaderView.ResizeMode.Stretch)

        boutons_selection = QHBoxLayout()
        self.bouton_tout = self._bouton("Tout sélectionner (filtrés)", self._tout_selectionner)
        self.bouton_aucun = self._bouton("Tout désélectionner", self._tout_deselectionner)
        boutons_selection.addWidget(self.bouton_tout)
        boutons_selection.addWidget(self.bouton_aucun)
        boutons_selection.addStretch(1)
        self.label_compte = QLabel("")
        boutons_selection.addWidget(self.label_compte)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.bouton_activer = self.buttons.addButton(
            "Activer la sélection", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.buttons.rejected.connect(self.reject)
        self.bouton_activer.clicked.connect(self._activer_selection)

        layout = QVBoxLayout(self)
        layout.addLayout(barre_filtre)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(boutons_selection)
        layout.addWidget(self.buttons)

        self._charger_comptes()

    def _bouton(self, texte: str, callback) -> QPushButton:
        bouton = QPushButton(texte, self)
        bouton.clicked.connect(callback)
        return bouton

    def _charger_comptes(self) -> None:
        query = QSqlQuery(self.db)
        query.exec(
            """
            SELECT c.code, c.libelle, c.classe
            FROM liste_des_comptes c
            WHERE NOT EXISTS (SELECT 1 FROM liste_des_comptes p WHERE p.parent_code = c.code)
              AND NOT EXISTS (SELECT 1 FROM plan_comptable pc WHERE pc.numero = c.code)
            ORDER BY c.code
            """
        )

        rows = []
        while query.next():
            rows.append((query.value(0), query.value(1), query.value(2)))

        self.table.setRowCount(len(rows))
        for row_index, (code, libelle, classe) in enumerate(rows):
            case = QTableWidgetItem()
            case.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            case.setCheckState(Qt.CheckState.Unchecked)
            case.setData(Qt.ItemDataRole.UserRole, code)
            self.table.setItem(row_index, COL_CASE, case)

            self.table.setItem(row_index, COL_CODE, QTableWidgetItem(code))
            self.table.setItem(row_index, COL_LIBELLE, QTableWidgetItem(libelle))
            self.table.setItem(row_index, COL_CLASSE, QTableWidgetItem(str(classe)))

            nature_combo = QComboBox(self.table)
            for valeur, libelle_nature in NATURE_LABELS.items():
                nature_combo.addItem(libelle_nature, valeur)
            nature_defaut = NATURE_PAR_DEFAUT_SELON_CLASSE.get(classe, "RESULTAT_BILAN")
            nature_combo.setCurrentIndex(nature_combo.findData(nature_defaut))
            self.table.setCellWidget(row_index, COL_NATURE, nature_combo)

            report_combo = QComboBox(self.table)
            for valeur, libelle_report in REPORT_A_NOUVEAU_LABELS.items():
                report_combo.addItem(libelle_report, valeur)
            report_defaut = report_a_nouveau_par_defaut(classe)
            report_combo.setCurrentIndex(report_combo.findData(report_defaut))
            self.table.setCellWidget(row_index, COL_REPORT, report_combo)

        self.table.itemChanged.connect(self._mettre_a_jour_compteur)
        self._mettre_a_jour_compteur()

    def _appliquer_filtre(self) -> None:
        texte = self.recherche.text().strip().lower()
        classe_filtre = self.filtre_classe.currentData()

        for row_index in range(self.table.rowCount()):
            code = self.table.item(row_index, COL_CODE).text().lower()
            libelle = self.table.item(row_index, COL_LIBELLE).text().lower()
            classe = int(self.table.item(row_index, COL_CLASSE).text())

            correspond_texte = texte in code or texte in libelle
            correspond_classe = classe_filtre is None or classe == classe_filtre
            self.table.setRowHidden(row_index, not (correspond_texte and correspond_classe))

    def _tout_selectionner(self) -> None:
        for row_index in range(self.table.rowCount()):
            if not self.table.isRowHidden(row_index):
                self.table.item(row_index, COL_CASE).setCheckState(Qt.CheckState.Checked)

    def _tout_deselectionner(self) -> None:
        for row_index in range(self.table.rowCount()):
            self.table.item(row_index, COL_CASE).setCheckState(Qt.CheckState.Unchecked)

    def _lignes_cochees(self) -> list[int]:
        return [
            row_index
            for row_index in range(self.table.rowCount())
            if self.table.item(row_index, COL_CASE).checkState() == Qt.CheckState.Checked
        ]

    def _mettre_a_jour_compteur(self, *_args) -> None:
        nb = len(self._lignes_cochees())
        self.label_compte.setText(f"{nb} compte(s) sélectionné(s)")

    def _activer_selection(self) -> None:
        lignes = self._lignes_cochees()
        if not lignes:
            QMessageBox.information(self, "Aucune sélection", "Sélectionnez au moins un compte à activer.")
            return

        self.db.transaction()
        insert_query = QSqlQuery(self.db)
        insert_query.prepare(
            "INSERT INTO plan_comptable (numero, intitule, nature, report_a_nouveau) VALUES (?, ?, ?, ?)"
        )
        for row_index in lignes:
            code = self.table.item(row_index, COL_CODE).text()
            libelle = self.table.item(row_index, COL_LIBELLE).text()
            nature = self.table.cellWidget(row_index, COL_NATURE).currentData()
            report = self.table.cellWidget(row_index, COL_REPORT).currentData()

            insert_query.addBindValue(code)
            insert_query.addBindValue(libelle)
            insert_query.addBindValue(nature)
            insert_query.addBindValue(report)
            if not insert_query.exec():
                self.db.rollback()
                QMessageBox.critical(
                    self, "Erreur", f"Échec de l'activation du compte {code} :\n{insert_query.lastError().text()}"
                )
                return

        self.db.commit()
        QMessageBox.information(self, "Comptes activés", f"{len(lignes)} compte(s) ajouté(s) au plan comptable.")
        self.accept()
