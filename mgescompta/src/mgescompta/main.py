"""Point d'entrée de l'application MgesCompta."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from mgescompta.db.database import init_db
from mgescompta.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    db = init_db()

    window = MainWindow(db)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
