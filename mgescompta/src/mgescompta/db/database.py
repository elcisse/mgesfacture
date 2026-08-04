"""Connexion SQLite (QtSql) et initialisation du schéma."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtSql import QSqlDatabase, QSqlQuery

from mgescompta.support.reference_interne import generer_reference_interne

DB_PATH = Path.home() / ".mgescompta" / "mgescompta.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
LISTE_DES_COMPTES_PATH = Path(__file__).parent / "data" / "liste_des_comptes.json"
REGIONS_DEPARTEMENTS_PATH = Path(__file__).parent / "data" / "regions_departements.json"
LOCALITES_DEFAUT_PATH = Path(__file__).parent / "data" / "localites_defaut.json"
PLAN_COMPTABLE_DEFAUT_PATH = Path(__file__).parent / "data" / "plan_comptable_defaut.json"
PLAN_TIERS_DEFAUT_PATH = Path(__file__).parent / "data" / "plan_tiers_defaut.json"
CONNECTION_NAME = "mgescompta"


def get_database(db_path: Path = DB_PATH) -> QSqlDatabase:
    if QSqlDatabase.contains(CONNECTION_NAME):
        return QSqlDatabase.database(CONNECTION_NAME)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = QSqlDatabase.addDatabase("QSQLITE", CONNECTION_NAME)
    db.setDatabaseName(str(db_path))
    if not db.open():
        raise RuntimeError(f"Impossible d'ouvrir la base : {db.lastError().text()}")

    QSqlQuery(db).exec("PRAGMA foreign_keys = ON")
    return db


NB_SAUVEGARDES_CONSERVEES = 20


def _sauvegarder_avant_migration(db_path: Path, nb_conservees: int = NB_SAUVEGARDES_CONSERVEES) -> None:
    """Copie de sécurité de la base, prise à chaque démarrage juste avant de
    lancer le schéma/les migrations -- pour pouvoir revenir en arrière à la
    main si une migration a un bug (déjà arrivé : un renommage de table
    cassant une clé étrangère). Rien à sauvegarder sur une toute première
    installation (fichier absent ou encore vide). sqlite3.backup() plutôt
    qu'une simple copie de fichier : correct même si la base a un journal de
    transaction actif, contrairement à une copie brute au niveau OS."""
    if not db_path.exists() or db_path.stat().st_size == 0:
        return

    dossier_backups = db_path.parent / "backups"
    dossier_backups.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    chemin_backup = dossier_backups / f"{db_path.stem}_{horodatage}{db_path.suffix}"

    source = sqlite3.connect(str(db_path))
    try:
        destination = sqlite3.connect(str(chemin_backup))
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    sauvegardes = sorted(dossier_backups.glob(f"{db_path.stem}_*{db_path.suffix}"))
    for ancienne in sauvegardes[:-nb_conservees]:
        ancienne.unlink()


def init_db(db_path: Path = DB_PATH) -> QSqlDatabase:
    db = get_database(db_path)
    _sauvegarder_avant_migration(db_path)

    lines = (
        line
        for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    )
    statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
    for statement in statements:
        query = QSqlQuery(db)
        if not query.exec(statement):
            raise RuntimeError(f"Échec du schéma SQL : {query.lastError().text()}\n{statement}")

    _migrer_plan_tiers_classification(db)
    _migrer_plan_comptable_actif(db)
    _migrer_type_adherent(db)
    _migrer_factures_annee_mois(db)
    _migrer_factures_id_source_externe(db)
    _migrer_factures_reference_interne(db)
    _migrer_operations_tiers_id(db)
    _migrer_operations_detail_paiement(db)

    seed_liste_des_comptes(db)
    seed_liste_des_journaux(db)
    seed_classification(db)
    seed_regions_departements(db)
    seed_localites(db)
    seed_plan_comptable_defaut(db)
    seed_plan_tiers_defaut(db)

    return db


def _migrer_plan_tiers_classification(db: QSqlDatabase) -> None:
    """CREATE TABLE IF NOT EXISTS n'ajoute pas de colonne à une table
    plan_tiers déjà créée avant l'introduction de classification_id/region_id/
    departement_id/localite_id -- on les ajoute ici si elles manquent encore."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(plan_tiers)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "classification_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE plan_tiers ADD COLUMN classification_id INTEGER REFERENCES classification(id)")
    if "region_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE plan_tiers ADD COLUMN region_id INTEGER REFERENCES region(id)")
    if "departement_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE plan_tiers ADD COLUMN departement_id INTEGER REFERENCES departement(id)")
    if "localite_id" not in noms:
        if "localite" in noms:
            # Ancien champ texte libre (remplacé par une vraie table de
            # référence localite, 1 département -> N localités).
            QSqlQuery(db).exec("ALTER TABLE plan_tiers DROP COLUMN localite")
        QSqlQuery(db).exec("ALTER TABLE plan_tiers ADD COLUMN localite_id INTEGER REFERENCES localite(id)")


def _migrer_plan_comptable_actif(db: QSqlDatabase) -> None:
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(plan_comptable)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "actif" not in noms:
        QSqlQuery(db).exec("ALTER TABLE plan_comptable ADD COLUMN actif INTEGER NOT NULL DEFAULT 1")


def _migrer_type_adherent(db: QSqlDatabase) -> None:
    """Le type de tiers CLIENT a été renommé ADHERENT (vocabulaire mutuelle
    de santé). SQLite ne permet pas de modifier une contrainte CHECK en
    place -- on reconstruit les 2 tables concernées (plan_tiers.type,
    modeles_saisie.necessite_tiers) en traduisant CLIENT -> ADHERENT au passage."""
    verif = QSqlQuery(db)
    verif.exec("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'plan_tiers'")
    verif.next()
    if "'CLIENT'" not in verif.value(0):
        return  # déjà migré

    QSqlQuery(db).exec("PRAGMA foreign_keys = OFF")
    db.transaction()

    QSqlQuery(db).exec("ALTER TABLE plan_tiers RENAME TO plan_tiers_ancien")
    QSqlQuery(db).exec(
        """
        CREATE TABLE plan_tiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL UNIQUE,
            intitule TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('ADHERENT', 'FOURNISSEUR', 'SALARIE', 'AUTRE')),
            compte_collectif TEXT NOT NULL,
            classification_id INTEGER REFERENCES classification(id),
            region_id INTEGER REFERENCES region(id),
            departement_id INTEGER REFERENCES departement(id),
            localite_id INTEGER REFERENCES localite(id),
            adresse TEXT,
            telephone TEXT,
            email TEXT,
            ninea TEXT,
            rc TEXT,
            actif INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    QSqlQuery(db).exec(
        """
        INSERT INTO plan_tiers
        SELECT id, numero, intitule,
               CASE WHEN type = 'CLIENT' THEN 'ADHERENT' ELSE type END,
               compte_collectif, classification_id, region_id, departement_id, localite_id,
               adresse, telephone, email, ninea, rc, actif, created_at, updated_at
        FROM plan_tiers_ancien
        """
    )
    QSqlQuery(db).exec("DROP TABLE plan_tiers_ancien")

    QSqlQuery(db).exec("ALTER TABLE modeles_saisie RENAME TO modeles_saisie_ancien")
    QSqlQuery(db).exec(
        """
        CREATE TABLE modeles_saisie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            nom TEXT NOT NULL,
            journal_type TEXT NOT NULL CHECK (journal_type IN ('ACHATS', 'VENTES', 'TRESORERIE', 'GENERAL', 'SITUATION')),
            necessite_tiers TEXT CHECK (necessite_tiers IN ('FOURNISSEUR', 'ADHERENT', 'SALARIE', 'AUTRE')),
            tiers_par_defaut_si_absent INTEGER NOT NULL DEFAULT 0,
            necessite_mode_paiement INTEGER NOT NULL DEFAULT 0,
            necessite_campagne INTEGER NOT NULL DEFAULT 0,
            actif INTEGER NOT NULL DEFAULT 1,
            ordre_affichage INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    QSqlQuery(db).exec(
        """
        INSERT INTO modeles_saisie
        SELECT id, code, nom, journal_type,
               CASE WHEN necessite_tiers = 'CLIENT' THEN 'ADHERENT' ELSE necessite_tiers END,
               tiers_par_defaut_si_absent, necessite_mode_paiement, necessite_campagne,
               actif, ordre_affichage, note, created_at, updated_at
        FROM modeles_saisie_ancien
        """
    )
    QSqlQuery(db).exec("DROP TABLE modeles_saisie_ancien")

    db.commit()
    QSqlQuery(db).exec("PRAGMA foreign_keys = ON")


def _migrer_factures_annee_mois(db: QSqlDatabase) -> None:
    """Ajoute (et rétro-remplit) la colonne annee_mois -- dérivée de
    date_facture (format 'yyyy-MM') -- pour les bases créées avant son
    introduction."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(factures)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "annee_mois" not in noms:
        QSqlQuery(db).exec("ALTER TABLE factures ADD COLUMN annee_mois TEXT NOT NULL DEFAULT ''")
    QSqlQuery(db).exec("UPDATE factures SET annee_mois = substr(date_facture, 1, 7) WHERE annee_mois = ''")
    QSqlQuery(db).exec("CREATE INDEX IF NOT EXISTS idx_factures_annee_mois ON factures(annee_mois)")


def _migrer_factures_id_source_externe(db: QSqlDatabase) -> None:
    """Ajoute id_source_externe (clé d'idempotence pour l'import CSV depuis
    mgesfacture) à une table factures créée avant son introduction. Index
    unique créé ici (pas dans schema.sql) : sinon il échouerait sur une base
    existante où la colonne n'a pas encore été ajoutée par l'ALTER ci-dessous."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(factures)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "id_source_externe" not in noms:
        QSqlQuery(db).exec("ALTER TABLE factures ADD COLUMN id_source_externe TEXT")
    QSqlQuery(db).exec(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factures_id_source_externe ON factures(id_source_externe)"
    )


def _migrer_factures_reference_interne(db: QSqlDatabase) -> None:
    """Ajoute reference_interne à une table factures créée avant son
    introduction, et rétro-génère une référence FC-AAAA-NNNNN (dans l'ordre
    chronologique date_facture puis id) pour les factures déjà existantes --
    y compris celles importées de mgesfacture avant l'introduction de cette
    fonctionnalité : leur référence F- d'origine n'est pas récupérable
    rétroactivement (jamais stockée côté mgescompta avant ce jour), elles
    reçoivent donc elles aussi une référence FC- locale."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(factures)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "reference_interne" not in noms:
        QSqlQuery(db).exec("ALTER TABLE factures ADD COLUMN reference_interne TEXT")

    a_generer = QSqlQuery(db)
    a_generer.exec(
        "SELECT id, date_facture FROM factures WHERE reference_interne IS NULL OR reference_interne = '' "
        "ORDER BY date_facture, id"
    )
    lignes = []
    while a_generer.next():
        lignes.append((a_generer.value(0), a_generer.value(1)))
    for facture_id, date_facture in lignes:
        annee = int((date_facture or "")[:4]) if (date_facture or "")[:4].isdigit() else 0
        reference = generer_reference_interne(db, annee)
        update = QSqlQuery(db)
        update.prepare("UPDATE factures SET reference_interne = ? WHERE id = ?")
        update.addBindValue(reference)
        update.addBindValue(facture_id)
        update.exec()

    QSqlQuery(db).exec("CREATE UNIQUE INDEX IF NOT EXISTS idx_factures_reference_interne ON factures(reference_interne)")


def _migrer_operations_tiers_id(db: QSqlDatabase) -> None:
    """Ajoute tiers_id à une table operations_comptables créée avant son
    introduction. Rattrape les opérations de constatation déjà existantes
    via factures.operation_constat_id (lien fiable) ; les anciens règlements
    restent tiers_id NULL faute de lien exploitable rétroactivement -- ils
    n'apparaîtront simplement pas dans "Voir les règlements" pour les bases
    migrées depuis une version antérieure à cette fonctionnalité."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(operations_comptables)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "tiers_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE operations_comptables ADD COLUMN tiers_id INTEGER REFERENCES plan_tiers(id)")

    QSqlQuery(db).exec(
        "UPDATE operations_comptables SET tiers_id = ("
        "SELECT f.tiers_id FROM factures f WHERE f.operation_constat_id = operations_comptables.id"
        ") WHERE tiers_id IS NULL AND id IN (SELECT operation_constat_id FROM factures)"
    )


def _migrer_operations_detail_paiement(db: QSqlDatabase) -> None:
    """Ajoute le détail du règlement (mode précis, banque/opérateur, numéro
    de compte, référence) à une table operations_comptables créée avant leur
    introduction. Pas de CHECK sur mode_paiement ici (ALTER TABLE ADD COLUMN
    ne le garantit pas de façon fiable sur toutes les versions de SQLite) --
    seules les nouvelles bases (schema.sql) l'imposent au niveau SQL, les
    autres s'appuient sur la validation applicative."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(operations_comptables)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "mode_paiement" not in noms:
        QSqlQuery(db).exec("ALTER TABLE operations_comptables ADD COLUMN mode_paiement TEXT")
    if "banque_operateur" not in noms:
        QSqlQuery(db).exec("ALTER TABLE operations_comptables ADD COLUMN banque_operateur TEXT")
    if "numero_compte" not in noms:
        QSqlQuery(db).exec("ALTER TABLE operations_comptables ADD COLUMN numero_compte TEXT")
    if "reference_paiement" not in noms:
        QSqlQuery(db).exec("ALTER TABLE operations_comptables ADD COLUMN reference_paiement TEXT")


def seed_liste_des_comptes(db: QSqlDatabase) -> None:
    """Importe le référentiel du plan comptable SYCEBNL (1133 comptes,
    classes 1-9) si la table est encore vide -- même source de données que
    le seeder ListeDesComptesSeeder du projet cger."""
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM liste_des_comptes")
    count_query.next()
    if count_query.value(0) > 0:
        return

    comptes = json.loads(LISTE_DES_COMPTES_PATH.read_text(encoding="utf-8"))

    # Désactivé le temps de l'insertion en lots : les lignes sont ordonnées
    # parent avant enfant dans le JSON, mais on sécurise quand même l'import
    # en lot -- même parti pris que le seeder cger d'origine.
    QSqlQuery(db).exec("PRAGMA foreign_keys = OFF")
    db.transaction()
    insert_query = QSqlQuery(db)
    insert_query.prepare(
        "INSERT INTO liste_des_comptes (code, libelle, classe, parent_code) VALUES (?, ?, ?, ?)"
    )
    for compte in comptes:
        insert_query.addBindValue(compte["code"])
        insert_query.addBindValue(compte["libelle"])
        insert_query.addBindValue(compte["classe"])
        insert_query.addBindValue(compte["parent_code"])
        if not insert_query.exec():
            db.rollback()
            QSqlQuery(db).exec("PRAGMA foreign_keys = ON")
            raise RuntimeError(f"Échec de l'import du plan comptable : {insert_query.lastError().text()}")
    db.commit()
    QSqlQuery(db).exec("PRAGMA foreign_keys = ON")


# Catalogue de référence des 5 types de journaux standards -- porté depuis
# ListeDesJournauxSeeder du projet cger.
JOURNAUX_REFERENCE: list[tuple[str, str, str]] = [
    ("ACHATS", "AC", "Achats"),
    ("VENTES", "VE", "Ventes"),
    ("TRESORERIE", "TR", "Trésorerie"),
    ("GENERAL", "OD", "Opérations diverses"),
    ("SITUATION", "AN", "À-nouveaux"),
]


def seed_liste_des_journaux(db: QSqlDatabase) -> None:
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM liste_des_journaux")
    count_query.next()
    if count_query.value(0) > 0:
        return

    insert_query = QSqlQuery(db)
    insert_query.prepare(
        "INSERT INTO liste_des_journaux (type, code, intitule, ordre_affichage) VALUES (?, ?, ?, ?)"
    )
    for ordre, (type_, code, intitule) in enumerate(JOURNAUX_REFERENCE):
        insert_query.addBindValue(type_)
        insert_query.addBindValue(code)
        insert_query.addBindValue(intitule)
        insert_query.addBindValue(ordre)
        if not insert_query.exec():
            raise RuntimeError(f"Échec de l'import des journaux : {insert_query.lastError().text()}")


# Classification des tiers -- essentiellement les types de prestataires de
# santé conventionnés par la mutuelle, plus un type générique "Fournisseur".
CLASSIFICATIONS_REFERENCE: dict[str, str] = {
    "CSA": "Centre de Santé",
    "POS": "Poste de Santé",
    "HOP": "Hôpital",
    "CAB": "Cabinet Privé",
    "CLI": "Clinique Privée",
    "LAB": "Laboratoire",
    "PHA": "Pharmacie",
    "CAP": "Centre d'Appareillage",
    "IMA": "Centre d'Imagerie Médicale",
    "FRN": "Fournisseur",
}


def seed_classification(db: QSqlDatabase) -> None:
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM classification")
    count_query.next()
    if count_query.value(0) > 0:
        return

    insert_query = QSqlQuery(db)
    insert_query.prepare("INSERT INTO classification (abrege, libelle) VALUES (?, ?)")
    for abrege, libelle in CLASSIFICATIONS_REFERENCE.items():
        insert_query.addBindValue(abrege)
        insert_query.addBindValue(libelle)
        if not insert_query.exec():
            raise RuntimeError(f"Échec de l'import des classifications : {insert_query.lastError().text()}")


def seed_regions_departements(db: QSqlDatabase) -> None:
    """Importe les régions et départements issus de
    "région et département.xlsx" si la table region est encore vide."""
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM region")
    count_query.next()
    if count_query.value(0) > 0:
        return

    regions = json.loads(REGIONS_DEPARTEMENTS_PATH.read_text(encoding="utf-8"))

    db.transaction()
    insert_region = QSqlQuery(db)
    insert_region.prepare("INSERT INTO region (code, nom) VALUES (?, ?)")
    insert_departement = QSqlQuery(db)
    insert_departement.prepare(
        "INSERT INTO departement (region_id, code, nom) VALUES (?, ?, ?)"
    )

    for region in regions:
        insert_region.addBindValue(region["code"])
        insert_region.addBindValue(region["nom"])
        if not insert_region.exec():
            db.rollback()
            raise RuntimeError(f"Échec de l'import des régions : {insert_region.lastError().text()}")
        region_id = insert_region.lastInsertId()

        for departement in region["departements"]:
            insert_departement.addBindValue(region_id)
            insert_departement.addBindValue(departement["code"])
            insert_departement.addBindValue(departement["nom"])
            if not insert_departement.exec():
                db.rollback()
                raise RuntimeError(f"Échec de l'import des départements : {insert_departement.lastError().text()}")

    db.commit()


def _resoudre_departement_id(db: QSqlDatabase, region_code: str, departement_code: str) -> int | None:
    query = QSqlQuery(db)
    query.prepare(
        "SELECT d.id FROM departement d JOIN region r ON r.id = d.region_id "
        "WHERE r.code = ? AND d.code = ?"
    )
    query.addBindValue(region_code)
    query.addBindValue(departement_code)
    query.exec()
    return query.value(0) if query.next() else None


def seed_localites(db: QSqlDatabase) -> None:
    """Importe un instantané des localités déjà saisies au fil de l'eau (pas
    de référentiel officiel équivalent à région et département : localite
    n'est alimentée que via le dialogue Tiers) -- seedé une seule fois, comme
    point de départ, si la table est encore vide. Fichier absent -> pas
    d'erreur, juste rien à faire (ex. build antérieure à cette fonctionnalité)."""
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM localite")
    count_query.next()
    if count_query.value(0) > 0 or not LOCALITES_DEFAUT_PATH.exists():
        return

    localites = json.loads(LOCALITES_DEFAUT_PATH.read_text(encoding="utf-8"))

    db.transaction()
    insert_query = QSqlQuery(db)
    insert_query.prepare("INSERT INTO localite (departement_id, nom) VALUES (?, ?)")
    for localite in localites:
        departement_id = _resoudre_departement_id(db, localite["region_code"], localite["departement_code"])
        if departement_id is None:
            continue  # département introuvable (référentiel régions/départements modifié depuis l'export)
        insert_query.addBindValue(departement_id)
        insert_query.addBindValue(localite["localite_nom"])
        if not insert_query.exec():
            db.rollback()
            raise RuntimeError(f"Échec de l'import des localités : {insert_query.lastError().text()}")
    db.commit()


def seed_plan_comptable_defaut(db: QSqlDatabase) -> None:
    """Importe un instantané du plan comptable de l'entreprise (comptes
    activés depuis le référentiel liste_des_comptes) -- seedé une seule fois,
    comme point de départ, si la table est encore vide."""
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM plan_comptable")
    count_query.next()
    if count_query.value(0) > 0 or not PLAN_COMPTABLE_DEFAUT_PATH.exists():
        return

    comptes = json.loads(PLAN_COMPTABLE_DEFAUT_PATH.read_text(encoding="utf-8"))

    db.transaction()
    insert_query = QSqlQuery(db)
    insert_query.prepare(
        "INSERT INTO plan_comptable (numero, intitule, nature, report_a_nouveau, actif) VALUES (?, ?, ?, ?, ?)"
    )
    for compte in comptes:
        insert_query.addBindValue(compte["numero"])
        insert_query.addBindValue(compte["intitule"])
        insert_query.addBindValue(compte["nature"])
        insert_query.addBindValue(compte["report_a_nouveau"])
        insert_query.addBindValue(compte["actif"])
        if not insert_query.exec():
            db.rollback()
            raise RuntimeError(f"Échec de l'import du plan comptable : {insert_query.lastError().text()}")
    db.commit()


def seed_plan_tiers_defaut(db: QSqlDatabase) -> None:
    """Importe un instantané des tiers déjà saisis -- seedé une seule fois,
    comme point de départ, si la table est encore vide. Résout les
    référentiels (classification/région/département/localité) par clé
    naturelle plutôt que par id brut, pour rester valide même si l'ordre
    d'auto-incrémentation diffère d'une base à l'autre."""
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM plan_tiers")
    count_query.next()
    if count_query.value(0) > 0 or not PLAN_TIERS_DEFAUT_PATH.exists():
        return

    tiers_liste = json.loads(PLAN_TIERS_DEFAUT_PATH.read_text(encoding="utf-8"))

    db.transaction()
    insert_query = QSqlQuery(db)
    insert_query.prepare(
        "INSERT INTO plan_tiers "
        "(numero, intitule, type, compte_collectif, classification_id, region_id, departement_id, localite_id, "
        "adresse, telephone, email, ninea, rc, actif) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    for tiers in tiers_liste:
        classification_id = None
        if tiers.get("classification_abrege"):
            classif_query = QSqlQuery(db)
            classif_query.prepare("SELECT id FROM classification WHERE abrege = ?")
            classif_query.addBindValue(tiers["classification_abrege"])
            classif_query.exec()
            classification_id = classif_query.value(0) if classif_query.next() else None

        region_id = None
        if tiers.get("region_code"):
            region_query = QSqlQuery(db)
            region_query.prepare("SELECT id FROM region WHERE code = ?")
            region_query.addBindValue(tiers["region_code"])
            region_query.exec()
            region_id = region_query.value(0) if region_query.next() else None

        departement_id = None
        if tiers.get("region_code") and tiers.get("departement_code"):
            departement_id = _resoudre_departement_id(db, tiers["region_code"], tiers["departement_code"])

        localite_id = None
        if departement_id is not None and tiers.get("localite_nom"):
            localite_query = QSqlQuery(db)
            localite_query.prepare("SELECT id FROM localite WHERE departement_id = ? AND nom = ?")
            localite_query.addBindValue(departement_id)
            localite_query.addBindValue(tiers["localite_nom"])
            localite_query.exec()
            localite_id = localite_query.value(0) if localite_query.next() else None

        insert_query.addBindValue(tiers["numero"])
        insert_query.addBindValue(tiers["intitule"])
        insert_query.addBindValue(tiers["type"])
        insert_query.addBindValue(tiers["compte_collectif"])
        insert_query.addBindValue(classification_id)
        insert_query.addBindValue(region_id)
        insert_query.addBindValue(departement_id)
        insert_query.addBindValue(localite_id)
        insert_query.addBindValue(tiers.get("adresse"))
        insert_query.addBindValue(tiers.get("telephone"))
        insert_query.addBindValue(tiers.get("email"))
        insert_query.addBindValue(tiers.get("ninea"))
        insert_query.addBindValue(tiers.get("rc"))
        insert_query.addBindValue(tiers.get("actif", 1))
        if not insert_query.exec():
            db.rollback()
            raise RuntimeError(f"Échec de l'import des tiers : {insert_query.lastError().text()}")
    db.commit()
