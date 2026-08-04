# MgesCompta

Application de gestion de comptabilité en partie double pour une seule
entreprise (PySide6 + SQLite), inspirée du modèle métier du projet
[cger](../cger) (Laravel/Livewire) : plan comptable, journaux, exercices
comptables, tiers, modèles de saisie, opérations/écritures comptables.
(cger gère plusieurs organisations via centres/organisations_professionnelles ;
cette couche multi-entreprise a été retirée ici, tout est global à l'appli.)

## Démarrage

```powershell
.venv\Scripts\pip install -e .
.venv\Scripts\python -m mgescompta.main
```

En développement, double-cliquer sur `run.bat` (ou l'exécuter depuis un
terminal) lance directement l'appli et garde la fenêtre de console ouverte
après fermeture pour lire d'éventuelles erreurs.

La base SQLite est créée automatiquement dans `%USERPROFILE%\.mgescompta\mgescompta.sqlite3`
à partir de `src/mgescompta/db/schema.sql`.

## État actuel

Squelette : schéma complet + une page de liste par module (`QSqlTableModel`).
Pas encore de formulaires de saisie ni de logique métier (équilibre
débit/crédit, validation d'opération, résolution des modèles de saisie).
