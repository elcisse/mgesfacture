"""Export des tiers vers un fichier CSV destiné à être importé dans
mgesfacture -- pour que les deux applis partagent le même référentiel
fournisseurs/adhérents sans ressaisie manuelle.

Colonnes en clé naturelle (numero, classification_abrege, region_code,
departement_code, localite_nom), pas en id brut -- les deux bases ont leurs
propres id auto-incrémentés, une clé naturelle reste valide même s'ils
diffèrent (même parti pris que les fichiers de seed *_defaut.json)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtSql import QSqlDatabase, QSqlQuery

COLONNES = [
    "numero",
    "intitule",
    "type",
    "compte_collectif",
    "classification_abrege",
    "region_code",
    "departement_code",
    "localite_nom",
    "adresse",
    "telephone",
    "email",
    "ninea",
    "rc",
    "actif",
]


@dataclass
class ResultatExportTiers:
    nb_tiers: int
    chemin: Path


def tiers_a_exporter(db: QSqlDatabase, uniquement_actifs: bool = True) -> list[dict]:
    requete = (
        "SELECT t.numero, t.intitule, t.type, t.compte_collectif, "
        "c.abrege, r.code, d.code, l.nom, t.adresse, t.telephone, t.email, t.ninea, t.rc, t.actif "
        "FROM plan_tiers t "
        "LEFT JOIN classification c ON c.id = t.classification_id "
        "LEFT JOIN region r ON r.id = t.region_id "
        "LEFT JOIN departement d ON d.id = t.departement_id "
        "LEFT JOIN localite l ON l.id = t.localite_id "
    )
    if uniquement_actifs:
        requete += "WHERE t.actif = 1 "
    requete += "ORDER BY t.numero"

    query = QSqlQuery(db)
    query.exec(requete)
    lignes = []
    while query.next():
        lignes.append(
            {
                "numero": query.value(0),
                "intitule": query.value(1),
                "type": query.value(2),
                "compte_collectif": query.value(3),
                "classification_abrege": query.value(4) or "",
                "region_code": query.value(5) or "",
                "departement_code": query.value(6) or "",
                "localite_nom": query.value(7) or "",
                "adresse": query.value(8) or "",
                "telephone": query.value(9) or "",
                "email": query.value(10) or "",
                "ninea": query.value(11) or "",
                "rc": query.value(12) or "",
                "actif": query.value(13),
            }
        )
    return lignes


def exporter_vers_csv(db: QSqlDatabase, chemin: Path, uniquement_actifs: bool = True) -> ResultatExportTiers:
    lignes = tiers_a_exporter(db, uniquement_actifs)
    with open(chemin, "w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES, delimiter=";")
        writer.writeheader()
        for ligne in lignes:
            writer.writerow(ligne)
    return ResultatExportTiers(nb_tiers=len(lignes), chemin=chemin)
