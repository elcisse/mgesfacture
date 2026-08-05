"""Vérification de mise à jour via les GitHub Releases du monorepo -- ne
considère que les tags préfixés "mgescompta-" (le dépôt contient aussi
mgesfacture). Dépôt public : lecture anonyme de l'API, pas de jeton à gérer.

Vérification manuelle seulement (menu Aide), jamais au démarrage : évite de
dépendre du réseau pour lancer l'appli, et n'informe jamais que -- aucun
téléchargement ni remplacement automatique de l'exécutable (remplacer un
.exe en cours d'exécution demande un vrai mécanisme dédié, pas juste un
appel réseau)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from mgescompta import __version__

DEPOT = "elcisse/mgesfacture"
PREFIXE_TAG = "mgescompta-"
URL_RELEASES = f"https://api.github.com/repos/{DEPOT}/releases"


@dataclass
class ResultatVerification:
    a_jour: bool
    version_locale: str
    version_distante: str | None = None
    url_release: str | None = None
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
    return ResultatVerification(
        a_jour=a_jour,
        version_locale=__version__,
        version_distante=version_distante,
        url_release=plus_recente.get("html_url"),
    )
