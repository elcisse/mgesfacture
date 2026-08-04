-- Référentiels partagés avec mgescompta (mêmes données, même structure) --
-- utiles pour que les tiers créés ici soient directement compatibles à
-- l'export/import, mais gérés indépendamment (chaque appli a sa propre base).
CREATE TABLE IF NOT EXISTS classification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    abrege TEXT NOT NULL UNIQUE,
    libelle TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS region (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    nom TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS departement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INTEGER NOT NULL REFERENCES region(id),
    code TEXT NOT NULL,
    nom TEXT NOT NULL,
    UNIQUE (region_id, code)
);
CREATE INDEX IF NOT EXISTS idx_departement_region ON departement(region_id);

-- Un département compte plusieurs localités (pas de seed : alimentée au fil
-- de l'eau depuis le dialogue Tiers, comme dans mgescompta).
CREATE TABLE IF NOT EXISTS localite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    departement_id INTEGER NOT NULL REFERENCES departement(id),
    nom TEXT NOT NULL,
    UNIQUE (departement_id, nom)
);
CREATE INDEX IF NOT EXISTS idx_localite_departement ON localite(departement_id);

-- Compte collectif par type de tiers : fixé une fois pour toutes dans les
-- Paramètres (Fichier > Paramètres…), pas ligne par ligne dans le dialogue
-- Tiers -- évite qu'un compte soit tapé différemment d'un tiers à l'autre.
CREATE TABLE IF NOT EXISTS parametres_comptes_collectifs (
    type TEXT PRIMARY KEY CHECK (type IN ('ADHERENT', 'FOURNISSEUR', 'SALARIE', 'AUTRE')),
    compte_collectif TEXT NOT NULL DEFAULT ''
);

-- Compte de charge par catégorie de fournisseur, fixé dans les Paramètres --
-- exporté avec chaque facture pour que mgescompta n'ait plus à le deviner à
-- l'import. SANTE = tiers classifié en prestataire de santé (tout sauf FRN,
-- ex. hôpitaux/pharmacies) ; FONCTIONNEMENT = fournisseur de biens et
-- services de fonctionnement (classification FRN, ou non classifié).
CREATE TABLE IF NOT EXISTS parametres_comptes_charge (
    categorie TEXT PRIMARY KEY CHECK (categorie IN ('SANTE', 'FONCTIONNEMENT')),
    compte_charge TEXT NOT NULL DEFAULT ''
);

-- Tiers : reprend le modèle de plan_tiers de mgescompta (numero + intitule +
-- type + compte_collectif + classification/région/département/localité),
-- pour que le rapprochement et l'import vers mgescompta se fassent sans
-- perte d'information. compte_collectif est un simple champ texte ici (pas
-- de plan comptable dans cette appli) -- charge à mgescompta de le
-- valider/corriger à l'import si besoin.
CREATE TABLE IF NOT EXISTS tiers (
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
);

-- Factures : simple enregistrement documentaire. Pas de montant_regle, pas
-- de statut de règlement, pas de lien vers une opération comptable --
-- cette appli est volontairement dépourvue de toute logique de
-- comptabilisation/règlement (contrairement au module Factures de mgescompta).
-- exportee_le : NULL tant que la facture n'a pas encore été exportée vers
-- mgescompta. Marquée (pas supprimée/déplacée) à l'export, pour qu'un
-- export ultérieur ne la reprenne jamais par accident.
-- uuid : identifiant globalement unique (pas l'id auto-incrémenté, qui n'est
-- unique que dans CETTE base) -- exporté comme clé d'idempotence, pour que
-- l'import reste fiable même si plusieurs machines/installations de
-- mgesfacture exportent vers le même mgescompta.
-- reference_interne : référence lisible attribuée à la création (jamais
-- modifiée ensuite), format F-AAAA-NNNNN, compteur remis à zéro chaque année
-- (année de date_facture) -- voir support/reference_interne.py. Propagée
-- telle quelle à l'export vers mgescompta (jamais régénérée côté mgescompta
-- pour une facture importée).
CREATE TABLE IF NOT EXISTS factures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT NOT NULL UNIQUE,
    tiers_id INTEGER NOT NULL REFERENCES tiers(id),
    reference_interne TEXT UNIQUE,
    numero_facture TEXT NOT NULL,
    date_facture TEXT NOT NULL,
    annee_mois TEXT NOT NULL DEFAULT '',
    date_echeance TEXT,
    libelle TEXT,
    montant REAL NOT NULL,
    exportee_le TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tiers_id, numero_facture)
);
CREATE INDEX IF NOT EXISTS idx_factures_tiers ON factures(tiers_id);
CREATE INDEX IF NOT EXISTS idx_factures_annee_mois ON factures(annee_mois);
