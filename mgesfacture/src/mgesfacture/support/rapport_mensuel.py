"""Rapport mensuel des factures : toutes les factures d'une période
(année-mois), regroupées par fournisseur avec sous-totaux, exportable en
PDF. Même mécanisme d'impression que le relevé de tiers de mgescompta
(QTextDocument + QPrinter, pas de dépendance PDF externe)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtSql import QSqlDatabase, QSqlQuery

from mgesfacture.support.formatage import formater_montant

MOIS_LABELS: dict[str, str] = {
    "01": "Janvier", "02": "Février", "03": "Mars", "04": "Avril",
    "05": "Mai", "06": "Juin", "07": "Juillet", "08": "Août",
    "09": "Septembre", "10": "Octobre", "11": "Novembre", "12": "Décembre",
}


def libelle_periode(annee_mois: str) -> str:
    """'2026-07' -> 'Juillet 2026' ; format inattendu renvoyé tel quel."""
    annee, _, mois = annee_mois.partition("-")
    return f"{MOIS_LABELS.get(mois, mois)} {annee}" if mois else annee_mois


@dataclass
class GroupeFournisseur:
    fournisseur_nom: str
    factures: list[dict] = field(default_factory=list)
    sous_total: float = 0.0


@dataclass
class RapportMensuel:
    annee_mois: str
    groupes: list[GroupeFournisseur] = field(default_factory=list)
    nb_factures: int = 0
    total_general: float = 0.0


def periodes_disponibles(db: QSqlDatabase) -> list[str]:
    """Toutes les année-mois ayant au moins une facture, les plus récentes
    d'abord -- pour peupler le sélecteur sans jamais proposer une période vide."""
    query = QSqlQuery(db)
    query.exec("SELECT DISTINCT annee_mois FROM factures ORDER BY annee_mois DESC")
    periodes = []
    while query.next():
        periodes.append(query.value(0))
    return periodes


def charger_rapport_mensuel(db: QSqlDatabase, annee_mois: str) -> RapportMensuel:
    query = QSqlQuery(db)
    query.prepare(
        "SELECT t.intitule, f.numero_facture, f.date_facture, f.reference_interne, f.montant "
        "FROM factures f JOIN tiers t ON t.id = f.tiers_id "
        "WHERE f.annee_mois = ? "
        "ORDER BY t.intitule, f.date_facture, f.id"
    )
    query.addBindValue(annee_mois)
    query.exec()

    groupes_par_fournisseur: dict[str, GroupeFournisseur] = {}
    ordre_fournisseurs: list[str] = []
    nb_factures = 0
    total_general = 0.0

    while query.next():
        fournisseur, numero_facture, date_facture, reference_interne, montant = (query.value(i) for i in range(5))
        if fournisseur not in groupes_par_fournisseur:
            groupes_par_fournisseur[fournisseur] = GroupeFournisseur(fournisseur_nom=fournisseur)
            ordre_fournisseurs.append(fournisseur)
        groupe = groupes_par_fournisseur[fournisseur]
        groupe.factures.append(
            {
                "numero_facture": numero_facture,
                "date_facture": date_facture,
                "reference_interne": reference_interne or "—",
                "montant": montant,
            }
        )
        groupe.sous_total = round(groupe.sous_total + montant, 2)
        nb_factures += 1
        total_general = round(total_general + montant, 2)

    return RapportMensuel(
        annee_mois=annee_mois,
        groupes=[groupes_par_fournisseur[nom] for nom in ordre_fournisseurs],
        nb_factures=nb_factures,
        total_general=total_general,
    )


def rapport_html(rapport: RapportMensuel) -> str:
    sections = []
    for groupe in rapport.groupes:
        lignes = "".join(
            f"<tr><td>{f['reference_interne']}</td><td>{f['numero_facture']}</td>"
            f"<td>{f['date_facture']}</td><td style='text-align:right'>{formater_montant(f['montant'])}</td></tr>"
            for f in groupe.factures
        )
        sections.append(
            f"<h2>{groupe.fournisseur_nom}</h2>"
            "<table>"
            "<tr><th>Référence</th><th>N° facture</th><th>Date</th><th>Montant</th></tr>"
            f"{lignes}"
            f"<tr class='sous-total'><td colspan='3'>Sous-total {groupe.fournisseur_nom}</td>"
            f"<td style='text-align:right'>{formater_montant(groupe.sous_total)}</td></tr>"
            "</table>"
        )
    corps = "".join(sections) or "<p><i>Aucune facture sur cette période.</i></p>"

    return f"""
    <html>
    <head><style>
        body {{ font-family: sans-serif; font-size: 11pt; }}
        h1 {{ font-size: 16pt; margin-bottom: 0; }}
        h2 {{ font-size: 12pt; margin-top: 20px; margin-bottom: 4px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #999; padding: 3px 6px; font-size: 9pt; }}
        th {{ background: #eee; text-align: left; }}
        .sous-total {{ font-weight: bold; background: #f5f5f5; }}
        .total {{ font-size: 13pt; font-weight: bold; margin-top: 20px; }}
    </style></head>
    <body>
        <h1>Rapport mensuel des factures</h1>
        <p>Période : {libelle_periode(rapport.annee_mois)}</p>
        {corps}
        <p class="total">Total général ({rapport.nb_factures} facture(s)) : {formater_montant(rapport.total_general)}</p>
    </body>
    </html>
    """


def imprimer_rapport_pdf(rapport: RapportMensuel, chemin: Path) -> None:
    document = QTextDocument()
    document.setHtml(rapport_html(rapport))

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(chemin))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(10, 15, 10, 15), QPageLayout.Unit.Millimeter)

    document.setPageSize(printer.pageRect(QPrinter.Unit.Point).size())
    document.print_(printer)
