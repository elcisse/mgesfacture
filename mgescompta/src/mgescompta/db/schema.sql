-- Schéma de mgescompta, inspiré du modèle comptable en partie double de
-- l'application cger (Laravel), simplifié pour une seule entreprise (pas de
-- multi-organisation : les tables centres/organisations_professionnelles et
-- les colonnes op_id de cger sont supprimées, tout est global à l'appli).
-- Adapté pour SQLite mono-fichier desktop :
-- - PK INTEGER AUTOINCREMENT au lieu d'UUID (pas de synchronisation
--   distribuée à gérer sur une appli desktop mono-poste).
-- - ENUM MySQL remplacés par CHECK (valeur IN (...)).
-- - Les FK auto-référencées (parent_code, annule_ecriture_id) sont
--   déclarées directement dans le CREATE TABLE : SQLite les accepte,
--   contrairement à MySQL qui impose de les ajouter après coup.

PRAGMA foreign_keys = ON;

-- Référentiel global du plan comptable (ex: SYSCOHADA), classé par classe
-- 1-8, avec hiérarchie parent_code -> code.
CREATE TABLE IF NOT EXISTS liste_des_comptes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    libelle TEXT NOT NULL,
    classe INTEGER NOT NULL,
    parent_code TEXT REFERENCES liste_des_comptes(code),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_comptes_classe ON liste_des_comptes(classe);

-- Référentiel global des types de journaux disponibles.
CREATE TABLE IF NOT EXISTS liste_des_journaux (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('ACHATS', 'VENTES', 'TRESORERIE', 'GENERAL', 'SITUATION')),
    code TEXT NOT NULL UNIQUE,
    intitule TEXT NOT NULL,
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Plan comptable de l'entreprise (dérivé du référentiel global).
CREATE TABLE IF NOT EXISTS plan_comptable (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL UNIQUE,
    intitule TEXT NOT NULL,
    nature TEXT NOT NULL CHECK (nature IN (
        'CAISSE', 'AMORTISSEMENT_PROVISION', 'RESULTAT_BILAN', 'CHARGE', 'PRODUIT',
        'RESULTAT_GESTION', 'IMMOBILISATION', 'CAPITAUX', 'STOCK', 'TITRE'
    )),
    report_a_nouveau TEXT NOT NULL CHECK (report_a_nouveau IN ('SOLDE_COMPTE', 'ECRITURES_NON_LETTREES')),
    actif INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Journaux ouverts pour l'entreprise (un par type au plus, en pratique).
CREATE TABLE IF NOT EXISTS code_journaux (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('ACHATS', 'VENTES', 'TRESORERIE', 'GENERAL', 'SITUATION')),
    code TEXT NOT NULL UNIQUE,
    intitule TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Exercices comptables (années fiscales) de l'entreprise.
CREATE TABLE IF NOT EXISTS exercices_comptables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    libelle TEXT NOT NULL UNIQUE,
    date_debut TEXT NOT NULL,
    date_fin TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'OUVERT' CHECK (statut IN ('OUVERT', 'CLOTURE')),
    cloture_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Classification des tiers (essentiellement les prestataires de santé
-- conventionnés : centres de santé, hôpitaux, pharmacies... plus un type
-- générique "Fournisseur" pour les autres tiers).
CREATE TABLE IF NOT EXISTS classification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    abrege TEXT NOT NULL UNIQUE,
    libelle TEXT NOT NULL
);

-- Tiers (adhérents/fournisseurs/salariés) de l'entreprise. compte_collectif
-- est une référence logique vers plan_comptable.numero, vérifiée au niveau
-- applicatif (pas de FK composite) -- même parti pris que cger.
CREATE TABLE IF NOT EXISTS plan_tiers (
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
);

-- Modèles de saisie : catalogue d'opérations pré-configurées pour guider la
-- saisie (ex: "Achat au comptant"), avec leurs lignes débit/crédit.
CREATE TABLE IF NOT EXISTS modeles_saisie (
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
);

CREATE TABLE IF NOT EXISTS modeles_saisie_lignes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modele_id INTEGER NOT NULL REFERENCES modeles_saisie(id) ON DELETE CASCADE,
    ordre INTEGER NOT NULL,
    sens TEXT NOT NULL CHECK (sens IN ('DEBIT', 'CREDIT')),
    type_compte TEXT NOT NULL CHECK (type_compte IN ('FIXE', 'TRESORERIE', 'TIERS')),
    compte_code TEXT,
    champ_montant TEXT NOT NULL DEFAULT 'montant'
);
CREATE INDEX IF NOT EXISTS idx_modeles_saisie_lignes_modele ON modeles_saisie_lignes(modele_id);

-- Opération comptable : l'en-tête d'une saisie (une ou plusieurs écritures).
-- tiers_id : NULL pour une opération de saisie libre (OD, etc.), renseigné
-- pour la comptabilisation/le règlement d'une facture -- indispensable pour
-- retrouver les règlements d'un tiers précis, puisque compte_collectif est
-- souvent partagé par convention entre plusieurs tiers du même type (ne
-- suffit pas seul à les distinguer).
-- mode_paiement/banque_operateur/numero_compte/reference_paiement : détail
-- du règlement (NULL pour une constatation ou une saisie libre, qui ne sont
-- pas des mouvements de trésorerie). mode_paiement va au-delà de
-- caisse/banque (ESPECES/CHEQUE/VIREMENT/MOBILE_MONEY) mais reste
-- purement descriptif -- le compte de trésorerie/journal réellement utilisé
-- continue de suivre la logique caisse (espèces) / banque (le reste).
CREATE TABLE IF NOT EXISTS operations_comptables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id INTEGER NOT NULL REFERENCES code_journaux(id),
    date TEXT NOT NULL,
    libelle TEXT NOT NULL,
    piece_reference TEXT,
    statut TEXT NOT NULL DEFAULT 'EN_ATTENTE' CHECK (statut IN ('EN_ATTENTE', 'VALIDEE', 'ANNULEE')),
    tiers_id INTEGER REFERENCES plan_tiers(id),
    mode_paiement TEXT CHECK (mode_paiement IN ('ESPECES', 'CHEQUE', 'VIREMENT', 'MOBILE_MONEY')),
    banque_operateur TEXT,
    numero_compte TEXT,
    reference_paiement TEXT,
    cree_par_id INTEGER REFERENCES utilisateurs(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_operations_date ON operations_comptables(date);

-- Écriture comptable : une ligne débit ou crédit d'une opération. Les
-- opérations sont validées automatiquement à la création (voir
-- support/saisie.py) ; la suppression d'écritures reste possible mais est
-- protégée par un contrôle d'équilibre applicatif (voir ui/ecritures_page.py)
-- -- annule_ecriture_id reste disponible pour qui préfère la contre-écriture
-- plutôt que la suppression directe. compte est une référence logique vers
-- plan_comptable.numero (même parti pris que plan_tiers.compte_collectif).
CREATE TABLE IF NOT EXISTS ecritures_comptables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL REFERENCES operations_comptables(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    libelle TEXT NOT NULL,
    compte TEXT NOT NULL,
    montant REAL NOT NULL,
    sens TEXT NOT NULL CHECK (sens IN ('DEBIT', 'CREDIT')),
    statut TEXT NOT NULL DEFAULT 'EN_ATTENTE' CHECK (statut IN ('EN_ATTENTE', 'VALIDEE', 'ANNULEE')),
    campagne TEXT,
    annule_ecriture_id INTEGER UNIQUE REFERENCES ecritures_comptables(id),
    cree_par_id INTEGER REFERENCES utilisateurs(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ecritures_date ON ecritures_comptables(date);

-- Facture fournisseur : document commercial distinct de l'écriture
-- comptable -- permet de suivre les factures en attente de paiement, leurs
-- échéances et règlements partiels, indépendamment de la comptabilisation.
-- operation_constat_id reste NULL tant que la facture n'a pas été
-- comptabilisée (voir support/factures.py) ; compte_charge est une
-- référence logique vers plan_comptable.numero (même parti pris que
-- plan_tiers.compte_collectif).
-- reference_interne : référence lisible, attribuée une seule fois (jamais
-- modifiée ensuite) -- voir support/reference_interne.py. Pour une facture
-- importée de mgesfacture, c'est SA référence (préfixe F-) qui est reprise
-- telle quelle ; pour une facture saisie directement ici, une référence
-- préfixée FC- est générée localement (préfixe distinct pour ne jamais
-- entrer en collision visuelle avec une référence importée).
CREATE TABLE IF NOT EXISTS factures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tiers_id INTEGER NOT NULL REFERENCES plan_tiers(id),
    reference_interne TEXT UNIQUE,
    numero_facture TEXT NOT NULL,
    date_facture TEXT NOT NULL,
    annee_mois TEXT NOT NULL DEFAULT '',
    date_echeance TEXT,
    compte_charge TEXT NOT NULL,
    libelle TEXT,
    montant REAL NOT NULL,
    montant_regle REAL NOT NULL DEFAULT 0,
    statut TEXT NOT NULL DEFAULT 'IMPAYEE' CHECK (statut IN ('IMPAYEE', 'PARTIELLEMENT_REGLEE', 'SOLDEE')),
    operation_constat_id INTEGER REFERENCES operations_comptables(id),
    -- Clé d'idempotence pour l'import depuis mgesfacture (id de la facture
    -- source) -- NULL pour les factures saisies directement ici. L'index
    -- unique associé est créé en migration (voir _migrer_factures_id_source_externe).
    id_source_externe TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tiers_id, numero_facture)
);
CREATE INDEX IF NOT EXISTS idx_factures_tiers ON factures(tiers_id);

-- Utilisateurs de l'application (traçabilité des saisies : cree_par_id).
-- Version simplifiée : pas d'auth web/rôles/permissions (hors périmètre
-- d'une appli desktop mono-poste pour l'instant).
CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    email TEXT UNIQUE,
    actif INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Découpage administratif (régions et départements), issu de
-- "région et département.xlsx".
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

-- Un département compte plusieurs localités.
CREATE TABLE IF NOT EXISTS localite (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    departement_id INTEGER NOT NULL REFERENCES departement(id),
    nom TEXT NOT NULL,
    UNIQUE (departement_id, nom)
);
CREATE INDEX IF NOT EXISTS idx_localite_departement ON localite(departement_id);
