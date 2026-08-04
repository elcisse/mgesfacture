"""Point d'entrée de l'application MgesFacture."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from mgesfacture.db.database import init_db
from mgesfacture.ui.icone import icone_ronde_verte
from mgesfacture.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    # Icône par défaut de l'appli : s'applique à toute fenêtre/dialogue qui
    # ne définit pas explicitement la sienne (donc toutes, ici).
    app.setWindowIcon(icone_ronde_verte())
    db = init_db()

    window = MainWindow(db)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
