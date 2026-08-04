"""Point d'entrée pour la construction de l'exécutable (PyInstaller) --
ajoute src/ au chemin d'import : le package n'est pas installé en
site-packages dans l'environnement de build, seulement en editable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from mgesfacture.main import main

if __name__ == "__main__":
    sys.exit(main())
