"""Import CSV de tiers exportés depuis mgescompta (voir export_tiers.py côté
mgescompta) -- pour partager le même référentiel fournisseurs/adhérents sans
ressaisie manuelle.

Idempotent par numero (identifiant métier stable, unique dans les deux
bases -- voir CODIFICATION.txt) : un tiers déjà présent localement n'est
jamais recréé ni mis à jour, seulement recompté en "déjà existants". Comme
pour l'import de factures, jamais de resynchronisation automatique -- un
tiers modifié localement ne doit jamais être silencieusement écrasé.

localite est ici alimentée "au fil de l'eau" (voir schema.sql) : une
localité absente localement est créée à la volée plutôt que de faire
échouer la ligne, contrairement à classification/région/département qui
sont un référentiel fixe partagé entre les deux applis (absence = vraie
anomalie, signalée en erreur)."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtSql import QSqlDatabase, QSqlQuery

COLONNES_ATTENDUES = [
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
class LigneErreur:
    numero_ligne: int
    numero: str
    message: str


@dataclass
class ResultatImportTiers:
    nb_importes: int = 0
    nb_deja_existants: int = 0
    erreurs: list[LigneErreur] = field(default_factory=list)


def _resoudre_classification_id(db: QSqlDatabase, abrege: str) -> int | None:
    if not abrege:
        return None
    query = QSqlQuery(db)
    query.prepare("SELECT id FROM classification WHERE abrege = ?")
    query.addBindValue(abrege)
    query.exec()
    return query.value(0) if query.next() else None


def _resoudre_region_id(db: QSqlDatabase, code: str) -> int | None:
    if not code:
        return None
    query = QSqlQuery(db)
    query.prepare("SELECT id FROM region WHERE code = ?")
    query.addBindValue(code)
    query.exec()
    return query.value(0) if query.next() else None


def _resoudre_departement_id(db: QSqlDatabase, region_id: int, code: str) -> int | None:
    if not code:
        return None
    query = QSqlQuery(db)
    query.prepare("SELECT id FROM departement WHERE region_id = ? AND code = ?")
    query.addBindValue(region_id)
    query.addBindValue(code)
    query.exec()
    return query.value(0) if query.next() else None


def _resoudre_ou_creer_localite_id(db: QSqlDatabase, departement_id: int, nom: str) -> int | None:
    if not nom:
        return None
    query = QSqlQuery(db)
    query.prepare("SELECT id FROM localite WHERE departement_id = ? AND nom = ?")
    query.addBindValue(departement_id)
    query.addBindValue(nom)
    query.exec()
    if query.next():
        return query.value(0)

    insertion = QSqlQuery(db)
    insertion.prepare("INSERT INTO localite (departement_id, nom) VALUES (?, ?)")
    insertion.addBindValue(departement_id)
    insertion.addBindValue(nom)
    if not insertion.exec():
        return None
    return insertion.lastInsertId()


def importer_csv(db: QSqlDatabase, chemin: Path) -> ResultatImportTiers:
    resultat = ResultatImportTiers()

    with open(chemin, newline="", encoding="utf-8-sig") as fichier:
        reader = csv.DictReader(fichier, delimiter=";")
        if reader.fieldnames != COLONNES_ATTENDUES:
            raise ValueError(
                f"Schéma de colonnes inattendu.\nAttendu : {COLONNES_ATTENDUES}\nTrouvé : {reader.fieldnames}"
            )

        for numero_ligne, row in enumerate(reader, start=2):
            try:
                numero = (row["numero"] or "").strip()
                if not numero:
                    resultat.erreurs.append(LigneErreur(numero_ligne, "", "Numéro manquant, ligne ignorée."))
                    continue

                deja = QSqlQuery(db)
                deja.prepare("SELECT 1 FROM tiers WHERE numero = ?")
                deja.addBindValue(numero)
                deja.exec()
                if deja.next():
                    resultat.nb_deja_existants += 1
                    continue

                intitule = (row["intitule"] or "").strip()
                if not intitule:
                    resultat.erreurs.append(LigneErreur(numero_ligne, numero, "Intitulé manquant."))
                    continue

                type_tiers = (row["type"] or "").strip()
                if type_tiers not in ("ADHERENT", "FOURNISSEUR", "SALARIE", "AUTRE"):
                    resultat.erreurs.append(LigneErreur(numero_ligne, numero, f"Type invalide : « {type_tiers} »."))
                    continue

                classification_abrege = (row["classification_abrege"] or "").strip()
                classification_id = _resoudre_classification_id(db, classification_abrege)
                if classification_abrege and classification_id is None:
                    resultat.erreurs.append(
                        LigneErreur(numero_ligne, numero, f"Classification introuvable : « {classification_abrege} ».")
                    )
                    continue

                region_code = (row["region_code"] or "").strip()
                region_id = _resoudre_region_id(db, region_code)
                if region_code and region_id is None:
                    resultat.erreurs.append(LigneErreur(numero_ligne, numero, f"Région introuvable : « {region_code} »."))
                    continue

                departement_code = (row["departement_code"] or "").strip()
                departement_id = None
                if departement_code:
                    if region_id is None:
                        resultat.erreurs.append(
                            LigneErreur(numero_ligne, numero, "Département fourni sans région correspondante.")
                        )
                        continue
                    departement_id = _resoudre_departement_id(db, region_id, departement_code)
                    if departement_id is None:
                        resultat.erreurs.append(
                            LigneErreur(numero_ligne, numero, f"Département introuvable : « {departement_code} ».")
                        )
                        continue

                localite_nom = (row["localite_nom"] or "").strip()
                localite_id = None
                if localite_nom:
                    if departement_id is None:
                        resultat.erreurs.append(
                            LigneErreur(numero_ligne, numero, "Localité fournie sans département correspondant.")
                        )
                        continue
                    localite_id = _resoudre_ou_creer_localite_id(db, departement_id, localite_nom)

                insertion = QSqlQuery(db)
                insertion.prepare(
                    "INSERT INTO tiers "
                    "(numero, intitule, type, compte_collectif, classification_id, region_id, departement_id, "
                    "localite_id, adresse, telephone, email, ninea, rc, actif) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                )
                insertion.addBindValue(numero)
                insertion.addBindValue(intitule)
                insertion.addBindValue(type_tiers)
                insertion.addBindValue((row["compte_collectif"] or "").strip())
                insertion.addBindValue(classification_id)
                insertion.addBindValue(region_id)
                insertion.addBindValue(departement_id)
                insertion.addBindValue(localite_id)
                insertion.addBindValue((row["adresse"] or "").strip() or None)
                insertion.addBindValue((row["telephone"] or "").strip() or None)
                insertion.addBindValue((row["email"] or "").strip() or None)
                insertion.addBindValue((row["ninea"] or "").strip() or None)
                insertion.addBindValue((row["rc"] or "").strip() or None)
                try:
                    actif = int(row["actif"])
                except (TypeError, ValueError):
                    actif = 1
                insertion.addBindValue(actif)

                if not insertion.exec():
                    resultat.erreurs.append(
                        LigneErreur(numero_ligne, numero, f"Échec d'insertion : {insertion.lastError().text()}")
                    )
                    continue

                resultat.nb_importes += 1
            except Exception as exc:  # défense en profondeur : jamais planter tout l'import pour une ligne
                resultat.erreurs.append(
                    LigneErreur(numero_ligne, (row.get("numero") or "").strip(), f"Erreur inattendue : {exc}")
                )

    return resultat
