"""Connexion SQLite (QtSql) et initialisation du schéma."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtSql import QSqlDatabase, QSqlQuery

from mgesfacture.support.reference_interne import generer_reference_interne

DB_PATH = Path.home() / ".mgesfacture" / "mgesfacture.sqlite3"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
REGIONS_DEPARTEMENTS_PATH = Path(__file__).parent / "data" / "regions_departements.json"
LOCALITES_DEFAUT_PATH = Path(__file__).parent / "data" / "localites_defaut.json"
TIERS_DEFAUT_PATH = Path(__file__).parent / "data" / "tiers_defaut.json"
CONNECTION_NAME = "mgesfacture"


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
    main si une migration a un bug (déjà arrivé côté mgescompta : un
    renommage de table cassant une clé étrangère). Rien à sauvegarder sur une
    toute première installation (fichier absent ou encore vide). sqlite3.
    backup() plutôt qu'une simple copie de fichier : correct même si la base
    a un journal de transaction actif, contrairement à une copie brute au
    niveau OS."""
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

    # Doit s'exécuter AVANT le passage du schéma : sinon "CREATE TABLE IF NOT
    # EXISTS tiers" créerait une table tiers neuve et vide (la table
    # fournisseurs existant encore par ailleurs), rendant tout renommage
    # ultérieur impossible.
    _migrer_fournisseurs_vers_tiers(db)

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

    # Complète une table tiers déjà migrée (issue de fournisseurs) mais
    # créée avant l'introduction des champs comptables/référentiels.
    _migrer_tiers_champs_referentiels(db)
    _migrer_tiers_intitule_non_unique(db)
    _migrer_factures_exportee_le(db)
    _migrer_factures_uuid(db)
    _migrer_factures_reference_interne(db)

    seed_classification(db)
    seed_regions_departements(db)
    seed_localites(db)
    seed_tiers_defaut(db)
    seed_parametres_comptes_collectifs(db)
    seed_parametres_comptes_charge(db)

    return db


def _migrer_fournisseurs_vers_tiers(db: QSqlDatabase) -> None:
    """La table fournisseurs (nom en texte libre) a été remplacée par tiers,
    calquée sur plan_tiers de mgescompta (numero + intitule + type), pour un
    rapprochement fiable lors de l'export/import des factures vers mgescompta."""
    verif = QSqlQuery(db)
    verif.exec("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'fournisseurs'")
    if not verif.next():
        return  # déjà migré, ou base neuve (schema.sql crée directement 'tiers')

    QSqlQuery(db).exec("PRAGMA foreign_keys = OFF")
    db.transaction()

    QSqlQuery(db).exec("ALTER TABLE fournisseurs RENAME TO tiers")
    QSqlQuery(db).exec("ALTER TABLE tiers RENAME COLUMN nom TO intitule")
    QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN numero TEXT NOT NULL DEFAULT ''")
    QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN type TEXT NOT NULL DEFAULT 'FOURNISSEUR'")
    QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN ninea TEXT")
    QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN rc TEXT")
    # Numéro provisoire pour les tiers déjà existants (T0001, T0002...) --
    # l'utilisateur peut ensuite l'ajuster manuellement si besoin.
    QSqlQuery(db).exec("UPDATE tiers SET numero = 'T' || substr('0000' || id, -4, 4) WHERE numero = ''")
    QSqlQuery(db).exec("CREATE UNIQUE INDEX IF NOT EXISTS idx_tiers_numero ON tiers(numero)")

    QSqlQuery(db).exec("ALTER TABLE factures RENAME COLUMN fournisseur_id TO tiers_id")
    QSqlQuery(db).exec("DROP INDEX IF EXISTS idx_factures_fournisseur")

    db.commit()
    QSqlQuery(db).exec("PRAGMA foreign_keys = ON")


def _migrer_tiers_champs_referentiels(db: QSqlDatabase) -> None:
    """Ajoute compte_collectif/classification_id/region_id/departement_id/
    localite_id à une table tiers créée avant leur introduction (ex. bases
    déjà migrées de fournisseurs -> tiers, sans ces colonnes)."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(tiers)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))

    if "compte_collectif" not in noms:
        QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN compte_collectif TEXT NOT NULL DEFAULT ''")
    if "classification_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN classification_id INTEGER REFERENCES classification(id)")
    if "region_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN region_id INTEGER REFERENCES region(id)")
    if "departement_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN departement_id INTEGER REFERENCES departement(id)")
    if "localite_id" not in noms:
        QSqlQuery(db).exec("ALTER TABLE tiers ADD COLUMN localite_id INTEGER REFERENCES localite(id)")


def _migrer_tiers_intitule_non_unique(db: QSqlDatabase) -> None:
    """La contrainte UNIQUE sur intitule vient de l'ancienne table
    fournisseurs (nom UNIQUE) -- ALTER TABLE RENAME COLUMN la préserve, mais
    deux tiers différents peuvent légitimement porter le même intitulé
    (numero est le vrai identifiant unique). SQLite ne permet pas de
    supprimer une contrainte UNIQUE sans reconstruire la table.

    Ordre important : on construit la table de remplacement sous un nom
    provisoire et on ne renomme JAMAIS la table 'tiers' existante -- SQLite
    réécrit automatiquement les clauses REFERENCES des autres tables (ex.
    factures.tiers_id) quand la table qu'elles visent est renommée, ce qui
    casserait irrémédiablement cette FK si 'tiers' était renommée puis
    remplacée (bug constaté : factures.tiers_id se retrouvait à référencer
    une table intermédiaire ensuite supprimée)."""
    verif = QSqlQuery(db)
    verif.exec("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tiers'")
    trouve = verif.next()
    contient_contrainte = trouve and "intitule TEXT NOT NULL UNIQUE" in (verif.value(0) or "")
    verif.finish()  # sinon le SELECT reste actif et "DROP TABLE tiers" échoue plus bas
    # ("database table is locked") -- QSqlQuery ne finalise pas toujours son
    # statement SQLite dès que le Python local sort de portée.
    if not contient_contrainte:
        return  # déjà migré, ou base neuve (schema.sql ne pose plus cette contrainte)

    QSqlQuery(db).exec("PRAGMA foreign_keys = OFF")
    db.transaction()

    creation = QSqlQuery(db)
    creation.exec(
        """
        CREATE TABLE tiers_nouveau (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL UNIQUE,
            intitule TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'FOURNISSEUR' CHECK (type IN ('ADHERENT', 'FOURNISSEUR', 'SALARIE', 'AUTRE')),
            compte_collectif TEXT NOT NULL DEFAULT '',
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
    creation.finish()
    copie = QSqlQuery(db)
    copie.exec(
        """
        INSERT INTO tiers_nouveau
        SELECT id, numero, intitule, type, compte_collectif, classification_id, region_id,
               departement_id, localite_id, adresse, telephone, email, ninea, rc, actif,
               created_at, updated_at
        FROM tiers
        """
    )
    copie.finish()  # le SELECT interne doit lui aussi être finalisé avant le DROP
    # 'tiers' est supprimée (pas renommée) : le texte REFERENCES tiers(id)
    # dans factures reste donc inchangé, et redevient valide dès que
    # tiers_nouveau est renommée à sa place juste après.
    suppression = QSqlQuery(db)
    if not suppression.exec("DROP TABLE tiers"):
        db.rollback()
        QSqlQuery(db).exec("PRAGMA foreign_keys = ON")
        raise RuntimeError(f"Échec de la migration tiers (DROP) : {suppression.lastError().text()}")
    suppression.finish()

    renommage = QSqlQuery(db)
    if not renommage.exec("ALTER TABLE tiers_nouveau RENAME TO tiers"):
        db.rollback()
        QSqlQuery(db).exec("PRAGMA foreign_keys = ON")
        raise RuntimeError(f"Échec de la migration tiers (RENAME) : {renommage.lastError().text()}")
    renommage.finish()

    QSqlQuery(db).exec("CREATE UNIQUE INDEX IF NOT EXISTS idx_tiers_numero ON tiers(numero)")

    db.commit()
    QSqlQuery(db).exec("PRAGMA foreign_keys = ON")


def _migrer_factures_exportee_le(db: QSqlDatabase) -> None:
    """Ajoute exportee_le à une table factures créée avant l'export vers
    mgescompta (NULL = jamais exportée, valeur par défaut correcte pour les
    factures déjà existantes -- elles n'ont, par définition, pas encore été
    exportées via ce mécanisme)."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(factures)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "exportee_le" not in noms:
        QSqlQuery(db).exec("ALTER TABLE factures ADD COLUMN exportee_le TEXT")


def _migrer_factures_uuid(db: QSqlDatabase) -> None:
    """Ajoute uuid (identifiant globalement unique, contrairement à id qui
    n'est unique que dans cette base) à une table factures créée avant son
    introduction, et rétro-génère un uuid pour les factures déjà existantes."""
    colonnes = QSqlQuery(db)
    colonnes.exec("PRAGMA table_info(factures)")
    noms = []
    while colonnes.next():
        noms.append(colonnes.value(1))
    if "uuid" not in noms:
        QSqlQuery(db).exec("ALTER TABLE factures ADD COLUMN uuid TEXT NOT NULL DEFAULT ''")

    a_generer = QSqlQuery(db)
    a_generer.exec("SELECT id FROM factures WHERE uuid = ''")
    ids = []
    while a_generer.next():
        ids.append(a_generer.value(0))
    for facture_id in ids:
        update = QSqlQuery(db)
        update.prepare("UPDATE factures SET uuid = ? WHERE id = ?")
        update.addBindValue(str(uuid.uuid4()))
        update.addBindValue(facture_id)
        update.exec()

    QSqlQuery(db).exec("CREATE UNIQUE INDEX IF NOT EXISTS idx_factures_uuid ON factures(uuid)")


def _migrer_factures_reference_interne(db: QSqlDatabase) -> None:
    """Ajoute reference_interne à une table factures créée avant son
    introduction, et rétro-génère une référence pour les factures déjà
    existantes -- dans l'ordre chronologique (date_facture, id), comme si
    elles avaient été saisies dans cet ordre."""
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


# Classification des tiers -- même référentiel que mgescompta, pour rester
# cohérent si des tiers sont un jour rapprochés/importés entre les deux bases.
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
    """Importe les régions et départements (même référentiel que mgescompta)
    si la table region est encore vide."""
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


def seed_tiers_defaut(db: QSqlDatabase) -> None:
    """Importe un instantané des tiers déjà saisis -- seedé une seule fois,
    comme point de départ, si la table est encore vide. Résout les
    référentiels (classification/région/département/localité) par clé
    naturelle plutôt que par id brut, pour rester valide même si l'ordre
    d'auto-incrémentation diffère d'une base à l'autre."""
    count_query = QSqlQuery(db)
    count_query.exec("SELECT COUNT(*) FROM tiers")
    count_query.next()
    if count_query.value(0) > 0 or not TIERS_DEFAUT_PATH.exists():
        return

    tiers_liste = json.loads(TIERS_DEFAUT_PATH.read_text(encoding="utf-8"))

    db.transaction()
    insert_query = QSqlQuery(db)
    insert_query.prepare(
        "INSERT INTO tiers "
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


# Compte collectif par défaut par type de tiers -- même convention que
# mgescompta (411000 pour un adhérent, 401100 pour un fournisseur). Ligne de
# base des Paramètres ; SALARIE/AUTRE restent vides tant qu'ils ne sont pas
# configurés manuellement (pas de convention établie pour ces types-là).
COMPTES_COLLECTIFS_PAR_DEFAUT: dict[str, str] = {
    "FOURNISSEUR": "401100",
    "ADHERENT": "411000",
    "SALARIE": "",
    "AUTRE": "",
}


def seed_parametres_comptes_collectifs(db: QSqlDatabase) -> None:
    """Initialise la ligne de paramètre (une par type de tiers) si elle
    n'existe pas encore, et rattrape les tiers déjà créés sans compte
    collectif (ex. juste après la migration qui a introduit ce paramétrage)."""
    for type_, valeur in COMPTES_COLLECTIFS_PAR_DEFAUT.items():
        count_query = QSqlQuery(db)
        count_query.prepare("SELECT COUNT(*) FROM parametres_comptes_collectifs WHERE type = ?")
        count_query.addBindValue(type_)
        count_query.exec()
        count_query.next()
        if count_query.value(0) > 0:
            continue
        insert_query = QSqlQuery(db)
        insert_query.prepare("INSERT INTO parametres_comptes_collectifs (type, compte_collectif) VALUES (?, ?)")
        insert_query.addBindValue(type_)
        insert_query.addBindValue(valeur)
        if not insert_query.exec():
            raise RuntimeError(f"Échec de l'initialisation des paramètres : {insert_query.lastError().text()}")

    QSqlQuery(db).exec(
        "UPDATE tiers SET compte_collectif = COALESCE("
        "(SELECT p.compte_collectif FROM parametres_comptes_collectifs p WHERE p.type = tiers.type), ''"
        ") WHERE compte_collectif = ''"
    )


# Compte de charge par défaut par catégorie -- 652000 reprend la convention
# déjà en place côté mgescompta pour les prestataires de santé classifiés.
# FONCTIONNEMENT n'a pas de convention établie : vide tant que non configuré.
COMPTES_CHARGE_PAR_DEFAUT: dict[str, str] = {
    "SANTE": "652000",
    "FONCTIONNEMENT": "",
}


def seed_parametres_comptes_charge(db: QSqlDatabase) -> None:
    for categorie, valeur in COMPTES_CHARGE_PAR_DEFAUT.items():
        count_query = QSqlQuery(db)
        count_query.prepare("SELECT COUNT(*) FROM parametres_comptes_charge WHERE categorie = ?")
        count_query.addBindValue(categorie)
        count_query.exec()
        count_query.next()
        if count_query.value(0) > 0:
            continue
        insert_query = QSqlQuery(db)
        insert_query.prepare("INSERT INTO parametres_comptes_charge (categorie, compte_charge) VALUES (?, ?)")
        insert_query.addBindValue(categorie)
        insert_query.addBindValue(valeur)
        if not insert_query.exec():
            raise RuntimeError(f"Échec de l'initialisation des paramètres : {insert_query.lastError().text()}")
