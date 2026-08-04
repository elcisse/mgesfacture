"""Export des factures vers un fichier CSV destiné à être importé dans
mgescompta.

Règles :
- Un fichier par export, schéma de colonnes fixe (voir COLONNES ci-dessous).
- Seules les factures pas encore exportées (exportee_le IS NULL) sont
  incluses -- une fois exportées, elles sont marquées (exportee_le = date du
  jour) pour ne plus jamais être reprises par un export ultérieur.
- id_source est l'UUID (identifiant globalement unique) de la facture dans
  mgesfacture -- PAS son id auto-incrémenté local, qui n'est unique que dans
  cette base et entrerait en collision si plusieurs machines/installations
  de mgesfacture exportent vers le même mgescompta. Sert de clé
  d'idempotence côté mgescompta, à ne pas confondre avec numero_facture qui
  peut se répéter.

Schéma des colonnes (dans cet ordre) :
    id_source       -- uuid de la facture dans mgesfacture (clé technique,
                       stable même entre plusieurs machines)
    reference_interne -- référence lisible attribuée à la création (F-AAAA-
                       NNNNN, voir support/reference_interne.py), reprise
                       telle quelle côté mgescompta -- jamais régénérée là-bas
                       pour une facture importée.
    tiers_numero    -- numero du tiers (plan_tiers.numero côté mgescompta)
    tiers_intitule  -- intitulé du tiers, pour vérification humaine
    compte_charge   -- résolu depuis Fichier > Paramètres… selon la
                       catégorie du fournisseur (santé/fonctionnement),
                       jamais deviné côté mgescompta
    numero_facture
    date_facture    -- yyyy-MM-dd
    date_echeance   -- yyyy-MM-dd, vide si non définie
    libelle         -- vide si non défini
    montant
    annee_mois      -- yyyy-MM, dérivé de date_facture
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtSql import QSqlDatabase, QSqlQuery

from mgesfacture.support.comptes_charge import compte_charge_pour_tiers

COLONNES = [
    "id_source",
    "reference_interne",
    "tiers_numero",
    "tiers_intitule",
    "compte_charge",
    "numero_facture",
    "date_facture",
    "date_echeance",
    "libelle",
    "montant",
    "annee_mois",
]


@dataclass
class ResultatExport:
    nb_factures: int
    chemin: Path


def factures_non_exportees(db: QSqlDatabase) -> list[dict]:
    """Chaque ligne porte une clé interne _facture_id (id local, pour le
    marquage exportee_le) en plus des colonnes exportées dans le CSV --
    DictWriter ignore les clés absentes de COLONNES, donc elle n'apparaît
    jamais dans le fichier."""
    query = QSqlQuery(db)
    query.exec(
        "SELECT f.id, f.uuid, t.id, t.numero, t.intitule, f.numero_facture, f.date_facture, "
        "f.date_echeance, f.libelle, f.montant, f.annee_mois, f.reference_interne "
        "FROM factures f JOIN tiers t ON t.id = f.tiers_id "
        "WHERE f.exportee_le IS NULL "
        "ORDER BY f.date_facture, f.id"
    )
    lignes = []
    while query.next():
        tiers_id = query.value(2)
        lignes.append(
            {
                "_facture_id": query.value(0),
                "id_source": query.value(1),
                "reference_interne": query.value(11),
                "tiers_numero": query.value(3),
                "tiers_intitule": query.value(4),
                "compte_charge": compte_charge_pour_tiers(db, tiers_id),
                "numero_facture": query.value(5),
                "date_facture": query.value(6),
                "date_echeance": query.value(7) or "",
                "libelle": query.value(8) or "",
                "montant": query.value(9),
                "annee_mois": query.value(10),
            }
        )
    return lignes


def exporter_vers_csv(db: QSqlDatabase, chemin: Path) -> ResultatExport:
    """Écrit les factures pas encore exportées dans chemin (CSV), puis les
    marque comme exportées. Si l'écriture du fichier échoue, rien n'est
    marqué (aucun risque de perdre la trace d'une facture jamais écrite)."""
    lignes = factures_non_exportees(db)

    with open(chemin, "w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for ligne in lignes:
            writer.writerow(ligne)

    if lignes:
        ids = [ligne["_facture_id"] for ligne in lignes]
        db.transaction()
        update = QSqlQuery(db)
        placeholders = ",".join("?" * len(ids))
        update.prepare(f"UPDATE factures SET exportee_le = datetime('now') WHERE id IN ({placeholders})")
        for id_ in ids:
            update.addBindValue(id_)
        if not update.exec():
            db.rollback()
            raise RuntimeError(f"Échec du marquage des factures exportées : {update.lastError().text()}")
        db.commit()

    return ResultatExport(nb_factures=len(lignes), chemin=chemin)
