"""Import CSV de factures exportées depuis mgesfacture.

Idempotent : chaque ligne porte un id_source -- l'UUID (globalement unique)
de la facture dans mgesfacture, PAS son id auto-incrémenté local (qui
entrerait en collision entre plusieurs machines/installations de
mgesfacture) ni son numero_facture (qui peut se répéter/être ressaisi
différemment). factures.id_source_externe est UNIQUE côté mgescompta --
rejouer le même fichier, ou importer les exports de plusieurs machines, ne
recrée donc jamais une facture déjà importée, elle est simplement recomptée
en "déjà importées".

Règles :
- Rapprochement du fournisseur par nom ET numéro, comparés exacts mais
  insensibles à la casse et aux accents (les deux doivent concorder). Si un
  tiers correspond par numéro mais pas par nom (ou l'inverse), c'est
  probablement une erreur de saisie -- signalé distinctement pour vérif
  humaine plutôt que résolu automatiquement à l'aveugle.
- Fournisseur introuvable -> ligne en erreur, listée pour traitement manuel,
  rien n'est inséré pour cette ligne. Jamais de création automatique de
  tiers : la numérotation officielle (CODIFICATION.txt) mérite une
  validation humaine.
- compte_charge est lu du fichier (fixé côté mgesfacture dans Fichier >
  Paramètres…, selon la catégorie santé/fonctionnement du fournisseur) --
  mgescompta ne le devine plus, il vérifie seulement qu'il existe bien dans
  le plan comptable (nature CHARGE). Absent ou invalide -> ligne en erreur.
- Qualité des données : toute ligne avec montant <= 0, date invalide ou
  numéro de facture vide est rejetée (jamais insérée) et signalée dans le
  rapport d'erreurs -- une ligne mal formée n'interrompt jamais l'import des
  autres lignes.
- annee_mois est toujours recalculé depuis date_facture, jamais copié du
  fichier (évite toute désynchronisation).
- Aucune facture importée n'est comptabilisée automatiquement.
- Après import : si une facture déjà importée a été modifiée dans mgesfacture
  depuis (montant, dates, numéro, libellé différents dans le fichier), on ne
  la met JAMAIS à jour automatiquement -- même si elle n'a pas encore été
  comptabilisée/réglée côté mgescompta. Elle est seulement signalée pour
  traitement manuel : une resynchro automatique pourrait silencieusement
  écraser une facture déjà comptabilisée/réglée, donc on ne le fait jamais,
  par cohérence, que ce soit le cas ou non.
"""
from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass, field
from datetime import date as date_cls
from pathlib import Path

from PySide6.QtSql import QSqlDatabase, QSqlQuery

from mgescompta.support.formatage import formater_montant
from mgescompta.support.reference_interne import generer_reference_interne


def _normaliser(texte: str | None) -> str:
    """Insensible à la casse et aux accents, pour comparer des noms/numéros
    saisis indépendamment dans les deux applications."""
    sans_accents = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode("ascii")
    return sans_accents.strip().casefold()


def _date_valide(texte: str) -> bool:
    try:
        date_cls.fromisoformat(texte)
        return True
    except (TypeError, ValueError):
        return False


COLONNES_ATTENDUES = [
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
class LigneErreur:
    numero_ligne: int
    id_source: str
    message: str


@dataclass
class ResultatImport:
    nb_importees: int = 0
    nb_deja_importees: int = 0
    erreurs: list[LigneErreur] = field(default_factory=list)
    modifiees: list[LigneErreur] = field(default_factory=list)


def _differences_avec_facture_existante(db: QSqlDatabase, id_source: str, row: dict) -> list[str]:
    """Compare une ligne du fichier à la facture déjà importée sous ce
    id_source_externe. Liste vide si rien n'a changé depuis le 1er import."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT numero_facture, date_facture, date_echeance, libelle, montant "
        "FROM factures WHERE id_source_externe = ?"
    )
    query.addBindValue(id_source)
    query.exec()
    if not query.next():
        return []
    numero_db, date_db, echeance_db, libelle_db, montant_db = (query.value(i) for i in range(5))

    numero_fichier = (row["numero_facture"] or "").strip()
    date_fichier = (row["date_facture"] or "").strip()
    echeance_fichier = (row["date_echeance"] or "").strip() or None
    libelle_fichier = (row["libelle"] or "").strip() or None
    try:
        montant_fichier = float(row["montant"])
    except (TypeError, ValueError):
        montant_fichier = None

    differences = []
    if (numero_db or "") != numero_fichier:
        differences.append(f"numéro « {numero_db} » -> « {numero_fichier} »")
    if (date_db or "") != date_fichier:
        differences.append(f"date « {date_db} » -> « {date_fichier} »")
    if (echeance_db or None) != echeance_fichier:
        differences.append(f"échéance « {echeance_db or '—'} » -> « {echeance_fichier or '—'} »")
    if (libelle_db or None) != libelle_fichier:
        differences.append(f"libellé « {libelle_db or '—'} » -> « {libelle_fichier or '—'} »")
    if montant_fichier is not None and round(montant_db, 2) != round(montant_fichier, 2):
        differences.append(f"montant {formater_montant(montant_db)} -> {formater_montant(montant_fichier)}")
    return differences


def _compte_charge_valide(db: QSqlDatabase, compte_charge: str) -> bool:
    """Le compte de charge vient du fichier (décidé côté mgesfacture) --
    on vérifie seulement qu'il existe bien dans le plan comptable, on ne
    devine jamais à sa place."""
    if not compte_charge:
        return False
    query = QSqlQuery(db)
    query.prepare("SELECT 1 FROM plan_comptable WHERE numero = ? AND nature = 'CHARGE'")
    query.addBindValue(compte_charge)
    query.exec()
    return query.next()


def _charger_fournisseurs(db: QSqlDatabase) -> list[tuple[int, str, str]]:
    """(id, numero, intitule) de tous les tiers FOURNISSEUR -- chargés une
    seule fois par import plutôt que requêtés ligne par ligne."""
    query = QSqlQuery(db)
    query.exec("SELECT id, numero, intitule FROM plan_tiers WHERE type = 'FOURNISSEUR'")
    fournisseurs = []
    while query.next():
        fournisseurs.append((query.value(0), query.value(1), query.value(2)))
    return fournisseurs


def _resoudre_fournisseur(
    fournisseurs: list[tuple[int, str, str]], tiers_numero: str, tiers_intitule: str
) -> tuple[int | None, str | None]:
    """Retourne (tiers_id, message_erreur) -- numéro ET nom doivent
    concorder (insensible casse/accents) pour résoudre automatiquement."""
    numero_norm = _normaliser(tiers_numero)
    intitule_norm = _normaliser(tiers_intitule)

    candidat_numero = None
    candidat_intitule = None
    for id_, numero_db, intitule_db in fournisseurs:
        meme_numero = _normaliser(numero_db) == numero_norm
        meme_intitule = _normaliser(intitule_db) == intitule_norm
        if meme_numero and meme_intitule:
            return id_, None
        if meme_numero:
            candidat_numero = (numero_db, intitule_db)
        if meme_intitule:
            candidat_intitule = (numero_db, intitule_db)

    if candidat_numero is not None:
        numero_db, intitule_db = candidat_numero
        return None, (
            f"Un tiers avec le numéro « {numero_db} » existe mais sous un nom différent "
            f"(« {intitule_db} » au lieu de « {tiers_intitule} »). Vérifiez manuellement."
        )
    if candidat_intitule is not None:
        numero_db, intitule_db = candidat_intitule
        return None, (
            f"Un tiers nommé « {intitule_db} » existe mais avec un numéro différent "
            f"(« {numero_db} » au lieu de « {tiers_numero} »). Vérifiez manuellement."
        )
    return None, (
        f"Fournisseur introuvable (numero « {tiers_numero} », nom « {tiers_intitule} »). "
        "Créez-le d'abord dans Tiers."
    )


def importer_csv(db: QSqlDatabase, chemin: Path) -> ResultatImport:
    resultat = ResultatImport()
    fournisseurs = _charger_fournisseurs(db)

    with open(chemin, newline="", encoding="utf-8-sig") as fichier:
        reader = csv.DictReader(fichier, delimiter=";")
        if reader.fieldnames != COLONNES_ATTENDUES:
            raise ValueError(
                f"Schéma de colonnes inattendu.\nAttendu : {COLONNES_ATTENDUES}\nTrouvé : {reader.fieldnames}"
            )

        for numero_ligne, row in enumerate(reader, start=2):
            # Toute la ligne est protégée : une erreur imprévue (pas
            # seulement les validations explicites ci-dessous) doit être
            # signalée dans le rapport, jamais interrompre l'import des
            # lignes suivantes.
            try:
                id_source = (row["id_source"] or "").strip()
                if not id_source:
                    resultat.erreurs.append(LigneErreur(numero_ligne, "", "id_source manquant, ligne ignorée."))
                    continue

                deja = QSqlQuery(db)
                deja.prepare("SELECT 1 FROM factures WHERE id_source_externe = ?")
                deja.addBindValue(id_source)
                deja.exec()
                if deja.next():
                    resultat.nb_deja_importees += 1
                    # Détecte une modification depuis le 1er import (montant,
                    # dates, numéro, libellé) -- jamais de mise à jour
                    # automatique, juste un signalement pour vérif manuelle
                    # (la facture a pu être comptabilisée/réglée entre-temps).
                    differences = _differences_avec_facture_existante(db, id_source, row)
                    if differences:
                        resultat.modifiees.append(
                            LigneErreur(
                                numero_ligne, id_source,
                                "Modifiée dans mgesfacture depuis son import (" + "; ".join(differences) + "). "
                                "Aucune resynchronisation automatique -- vérifiez et mettez à jour manuellement "
                                "dans mgescompta si besoin.",
                            )
                        )
                    continue

                tiers_numero = (row["tiers_numero"] or "").strip()
                tiers_intitule = (row["tiers_intitule"] or "").strip()
                tiers_id, erreur_fournisseur = _resoudre_fournisseur(fournisseurs, tiers_numero, tiers_intitule)
                if tiers_id is None:
                    resultat.erreurs.append(LigneErreur(numero_ligne, id_source, erreur_fournisseur))
                    continue

                numero_facture = (row["numero_facture"] or "").strip()
                if not numero_facture:
                    resultat.erreurs.append(LigneErreur(numero_ligne, id_source, "Numéro de facture vide."))
                    continue

                date_facture = (row["date_facture"] or "").strip()
                if not _date_valide(date_facture):
                    resultat.erreurs.append(
                        LigneErreur(
                            numero_ligne, id_source, f"Date de facture invalide : « {date_facture or '(vide)'} »."
                        )
                    )
                    continue

                date_echeance = (row["date_echeance"] or "").strip() or None
                if date_echeance is not None and not _date_valide(date_echeance):
                    resultat.erreurs.append(
                        LigneErreur(numero_ligne, id_source, f"Date d'échéance invalide : « {date_echeance} ».")
                    )
                    continue

                try:
                    montant = float(row["montant"])
                except (TypeError, ValueError):
                    resultat.erreurs.append(LigneErreur(numero_ligne, id_source, "Montant invalide."))
                    continue
                if montant <= 0:
                    resultat.erreurs.append(
                        LigneErreur(numero_ligne, id_source, "Le montant doit être supérieur à zéro.")
                    )
                    continue

                compte_charge = (row["compte_charge"] or "").strip()
                if not _compte_charge_valide(db, compte_charge):
                    resultat.erreurs.append(
                        LigneErreur(
                            numero_ligne, id_source,
                            f"Compte de charge « {compte_charge or '(vide)'} » introuvable dans le plan comptable "
                            "(nature Charge). Corrigez le paramétrage dans Fichier > Paramètres… côté mgesfacture "
                            "et réexportez, ou créez la facture manuellement ici.",
                        )
                    )
                    continue

                libelle = (row["libelle"] or "").strip() or None
                annee_mois = date_facture[:7]

                # La référence F-... d'origine (attribuée à la création dans
                # mgesfacture) est reprise telle quelle -- jamais régénérée
                # ici. Filet de sécurité seulement : un fichier issu d'une
                # version de mgesfacture antérieure à cette fonctionnalité
                # n'aurait normalement pas le bon schéma de colonnes et
                # serait déjà rejeté plus haut, mais on ne veut jamais
                # insérer une chaîne vide dans une colonne UNIQUE.
                reference_interne = (row["reference_interne"] or "").strip()
                if not reference_interne:
                    reference_interne = generer_reference_interne(db, int(annee_mois[:4]))

                insertion = QSqlQuery(db)
                insertion.prepare(
                    "INSERT INTO factures "
                    "(reference_interne, tiers_id, numero_facture, date_facture, annee_mois, date_echeance, "
                    "compte_charge, libelle, montant, id_source_externe) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                )
                insertion.addBindValue(reference_interne)
                insertion.addBindValue(tiers_id)
                insertion.addBindValue(numero_facture)
                insertion.addBindValue(date_facture)
                insertion.addBindValue(annee_mois)
                insertion.addBindValue(date_echeance)
                insertion.addBindValue(compte_charge)
                insertion.addBindValue(libelle)
                insertion.addBindValue(montant)
                insertion.addBindValue(id_source)
                if not insertion.exec():
                    resultat.erreurs.append(
                        LigneErreur(numero_ligne, id_source, f"Échec d'insertion : {insertion.lastError().text()}")
                    )
                    continue

                resultat.nb_importees += 1
            except Exception as exc:  # défense en profondeur : jamais planter tout l'import pour une ligne
                resultat.erreurs.append(
                    LigneErreur(numero_ligne, (row.get("id_source") or "").strip(), f"Erreur inattendue : {exc}")
                )

    return resultat
