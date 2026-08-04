"""Page de liste générique : QTableView branché sur un QSqlTableModel (ou
QSqlRelationalTableModel si des relations sont fournies, pour afficher le
libellé d'une table liée plutôt que l'identifiant brut d'une clé étrangère)."""
from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtSql import QSqlDatabase, QSqlRelation, QSqlRelationalTableModel, QSqlTableModel
from PySide6.QtWidgets import QHeaderView, QLabel, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget

from mgescompta.support.formatage import formater_montant


class _DelegateMontant(QStyledItemDelegate):
    """Affiche la valeur brute d'une colonne montant au format devise de
    l'application (FCFA, espace en séparateur de milliers, sans décimale)."""

    def displayText(self, value, locale: QLocale) -> str:
        return formater_montant(value)


class SqlTablePage(QWidget):
    def __init__(
        self,
        db: QSqlDatabase,
        table: str,
        titre: str,
        colonnes: dict[str, str] | None = None,
        parent: QWidget | None = None,
        relations: dict[str, tuple[str, str]] | None = None,
        tri: str | None = None,
        colonnes_montant: set[str] | None = None,
    ) -> None:
        """colonnes: {nom_colonne_sql: libelle_affiche} pour renommer/limiter
        les colonnes visibles ; si None, toutes les colonnes de la table sont
        affichées avec leur nom SQL.
        relations: {nom_colonne_fk: (table_liee, colonne_affichee)} -- affiche
        le libellé de la table liée à la place de l'identifiant brut.
        tri: nom de la colonne SQL utilisée pour le tri initial (ordre croissant).
        colonnes_montant: noms des colonnes à afficher au format devise
        (FCFA, espace en séparateur de milliers, sans décimale)."""
        super().__init__(parent)

        if relations:
            self.model = QSqlRelationalTableModel(self, db)
            self.model.setTable(table)
        else:
            self.model = QSqlTableModel(self, db)
            self.model.setTable(table)
        self.model.setEditStrategy(QSqlTableModel.EditStrategy.OnFieldChange)

        # Résolu AVANT setRelation : une fois la relation posée, le champ
        # perd son nom SQL d'origine (ex. classification_id -> libelle) dans
        # model.record(), donc on fige ici la correspondance position <-> libellé.
        colonnes_visibles: dict[int, str] = {}
        if colonnes:
            for nom_colonne, libelle in colonnes.items():
                index = self.model.fieldIndex(nom_colonne)
                if index >= 0:
                    colonnes_visibles[index] = libelle

        index_colonnes_montant: list[int] = []
        if colonnes_montant:
            for nom_colonne in colonnes_montant:
                index = self.model.fieldIndex(nom_colonne)
                if index >= 0:
                    index_colonnes_montant.append(index)

        if relations:
            self.model.setJoinMode(QSqlRelationalTableModel.JoinMode.LeftJoin)
            for nom_colonne, (table_liee, colonne_affichee) in relations.items():
                index = self.model.fieldIndex(nom_colonne)
                self.model.setRelation(index, QSqlRelation(table_liee, "id", colonne_affichee))

        for index, libelle in colonnes_visibles.items():
            self.model.setHeaderData(index, Qt.Orientation.Horizontal, libelle)

        if tri:
            index_tri = self.model.fieldIndex(tri)
            if index_tri >= 0:
                self.model.setSort(index_tri, Qt.SortOrder.AscendingOrder)

        self.model.select()

        self.view = QTableView(self)
        self.view.setModel(self.model)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        # Aucune modification directe dans la table : toute création/édition
        # passe par les dialogues dédiés (validation, règles métier).
        self.view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        # Interactive (et non Stretch) pour permettre le redimensionnement
        # des colonnes à la souris ; la dernière colonne comble l'espace restant.
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)

        if index_colonnes_montant:
            self._delegate_montant = _DelegateMontant(self.view)
            for index in index_colonnes_montant:
                self.view.setItemDelegateForColumn(index, self._delegate_montant)

        if colonnes:
            for index in range(self.model.columnCount()):
                if index not in colonnes_visibles:
                    self.view.hideColumn(index)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<h2>{titre}</h2>"))
        layout.addWidget(self.view)

    def refresh(self) -> None:
        self.model.select()
