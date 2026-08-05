"""Vérification ET installation de mise à jour via les GitHub Releases du
monorepo -- ne considère que les tags préfixés "mgescompta-" (le dépôt
contient aussi mgesfacture). Dépôt public : lecture anonyme de l'API, pas de
jeton à gérer.

Vérification manuelle seulement (menu Aide), jamais au démarrage : évite de
dépendre du réseau pour lancer l'appli. L'installation automatique n'est
proposée que si l'appli tourne en exécutable figé (PyInstaller, sys.frozen)
-- en mode développement, il n'y a pas de .exe unique à remplacer, on se
contente d'indiquer le lien.

Mécanisme d'installation (remplacer un .exe EN COURS D'EXÉCUTION) :
Windows autorise le renommage/déplacement d'un fichier .exe pendant qu'il
s'exécute (contrairement à l'écriture directe dessus) -- PyInstaller ouvre
son propre binaire avec un partage qui permet ça. On renomme donc l'exe
courant en .old, on met le fichier téléchargé à sa place, on relance un
nouveau processus sur ce chemin, puis on quitte l'ancien. Le .old reste
verrouillé tant que l'ancien processus tourne encore -- nettoyé par
nettoyer_ancienne_version() au démarrage suivant, une fois le verrou levé."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from mgescompta import __version__

DEPOT = "elcisse/mgesfacture"
PREFIXE_TAG = "mgescompta-"
NOM_EXE = "mgescompta.exe"
URL_RELEASES = f"https://api.github.com/repos/{DEPOT}/releases"


@dataclass
class ResultatVerification:
    a_jour: bool
    version_locale: str
    version_distante: str | None = None
    url_release: str | None = None
    url_asset: str | None = None
    erreur: str | None = None


def _version_en_tuple(version: str) -> tuple[int, ...]:
    """'1.2.0' -> (1, 2, 0) ; segments non numériques ignorés (ex. suffixe -beta)."""
    segments = []
    for partie in version.split("."):
        chiffres = "".join(c for c in partie if c.isdigit())
        segments.append(int(chiffres) if chiffres else 0)
    return tuple(segments)


def verifier_mise_a_jour(timeout: float = 5.0) -> ResultatVerification:
    try:
        requete = urllib.request.Request(URL_RELEASES, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            releases = json.loads(reponse.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as erreur:
        return ResultatVerification(a_jour=True, version_locale=__version__, erreur=str(erreur))

    candidates = [r for r in releases if r.get("tag_name", "").startswith(PREFIXE_TAG) and not r.get("draft")]
    if not candidates:
        return ResultatVerification(a_jour=True, version_locale=__version__)

    # /releases renvoie les releases les plus récentes en premier.
    plus_recente = candidates[0]
    version_distante = plus_recente["tag_name"][len(PREFIXE_TAG):].lstrip("v")

    a_jour = _version_en_tuple(version_distante) <= _version_en_tuple(__version__)

    url_asset = None
    for asset in plus_recente.get("assets", []):
        if asset.get("name", "").lower() == NOM_EXE:
            url_asset = asset.get("browser_download_url")
            break

    return ResultatVerification(
        a_jour=a_jour,
        version_locale=__version__,
        version_distante=version_distante,
        url_release=plus_recente.get("html_url"),
        url_asset=url_asset,
    )


def telecharger_et_installer(url_asset: str, chemin_exe_actuel: Path, timeout: float = 120.0) -> None:
    """Télécharge le nouvel exécutable et le met en place à côté de
    chemin_exe_actuel, qui EST le fichier en cours d'exécution -- ne
    l'écrase jamais directement (verrouillé), le renomme de côté puis pose
    le nouveau fichier à sa place. Après cet appel, chemin_exe_actuel pointe
    vers la nouvelle version ; le processus courant continue de tourner sur
    l'ancienne (déjà chargée en mémoire) jusqu'à son prochain redémarrage."""
    chemin_nouveau = chemin_exe_actuel.parent / f"{chemin_exe_actuel.stem}.new{chemin_exe_actuel.suffix}"
    chemin_ancien = chemin_exe_actuel.parent / f"{chemin_exe_actuel.stem}.old{chemin_exe_actuel.suffix}"

    requete = urllib.request.Request(url_asset)
    with urllib.request.urlopen(requete, timeout=timeout) as reponse, open(chemin_nouveau, "wb") as fichier:
        while True:
            morceau = reponse.read(256 * 1024)
            if not morceau:
                break
            fichier.write(morceau)

    if chemin_ancien.exists():
        chemin_ancien.unlink()  # reliquat d'une mise à jour précédente non nettoyé
    os.replace(chemin_exe_actuel, chemin_ancien)
    os.replace(chemin_nouveau, chemin_exe_actuel)


def nettoyer_ancienne_version(chemin_exe_actuel: Path) -> None:
    """À appeler au démarrage : supprime le .old laissé par une mise à jour
    précédente. Le processus qui le tenait verrouillé a fini par se fermer
    (on ne serait pas en train de redémarrer sinon), donc normalement libre
    -- mais échec silencieux si jamais ce n'est pas encore le cas (antivirus
    qui scanne encore le fichier, etc.), on réessaiera au prochain démarrage."""
    chemin_ancien = chemin_exe_actuel.parent / f"{chemin_exe_actuel.stem}.old{chemin_exe_actuel.suffix}"
    if chemin_ancien.exists():
        try:
            chemin_ancien.unlink()
        except OSError:
            pass
