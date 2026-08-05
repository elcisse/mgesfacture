"""Point d'entrée de l'application MgesCompta."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from mgescompta.db.database import init_db
from mgescompta.support.mise_a_jour import nettoyer_ancienne_version
from mgescompta.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    # Reliquat d'une mise à jour auto-installée au run précédent (voir
    # support/mise_a_jour.py) -- ne s'applique qu'en exécutable figé, il n'y
    # a pas de .exe unique à nettoyer en mode développement.
    if getattr(sys, "frozen", False):
        nettoyer_ancienne_version(Path(sys.executable))

    db = init_db()

    window = MainWindow(db)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
