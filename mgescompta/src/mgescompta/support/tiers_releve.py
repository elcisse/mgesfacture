"""Relevé d'un tiers : coordonnées, factures, règlements et solde --
utilisé par l'aperçu à l'écran et par l'export PDF (même source de données,
pour ne jamais afficher autre chose que ce qui est imprimé)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtSql import QSqlDatabase, QSqlQuery

from mgescompta.support.formatage import formater_montant

STATUT_LABELS: dict[str, str] = {
    "IMPAYEE": "Impayée",
    "PARTIELLEMENT_REGLEE": "Partiellement réglée",
    "SOLDEE": "Soldée",
}

MODE_PAIEMENT_LABELS: dict[str, str] = {
    "ESPECES": "Espèces",
    "CHEQUE": "Chèque",
    "VIREMENT": "Virement bancaire",
    "MOBILE_MONEY": "Mobile Money",
}


@dataclass
class InfosTiers:
    numero: str
    intitule: str
    type: str
    compte_collectif: str
    adresse: str | None
    telephone: str | None
    email: str | None
    classification: str | None
    region: str | None
    departement: str | None
    localite: str | None
    actif: bool


@dataclass
class ReleveTiers:
    infos: InfosTiers
    factures: list[dict] = field(default_factory=list)
    reglements: list[dict] = field(default_factory=list)
    solde_du: float = 0.0


def charger_infos_tiers(db: QSqlDatabase, tiers_id: int) -> InfosTiers | None:
    query = QSqlQuery(db)
    query.prepare(
        "SELECT t.numero, t.intitule, t.type, t.compte_collectif, t.adresse, t.telephone, t.email, "
        "c.libelle, r.nom, d.nom, l.nom, t.actif "
        "FROM plan_tiers t "
        "LEFT JOIN classification c ON c.id = t.classification_id "
        "LEFT JOIN region r ON r.id = t.region_id "
        "LEFT JOIN departement d ON d.id = t.departement_id "
        "LEFT JOIN localite l ON l.id = t.localite_id "
        "WHERE t.id = ?"
    )
    query.addBindValue(tiers_id)
    query.exec()
    if not query.next():
        return None
    return InfosTiers(
        numero=query.value(0),
        intitule=query.value(1),
        type=query.value(2),
        compte_collectif=query.value(3),
        adresse=query.value(4) or None,
        telephone=query.value(5) or None,
        email=query.value(6) or None,
        classification=query.value(7) or None,
        region=query.value(8) or None,
        departement=query.value(9) or None,
        localite=query.value(10) or None,
        actif=bool(query.value(11)),
    )


def factures_tiers(db: QSqlDatabase, tiers_id: int) -> list[dict]:
    """Toutes les factures du tiers (tous statuts), les plus récentes
    d'abord -- pour l'aperçu/relevé, contrairement à factures_a_regler qui
    ne liste que celles restant à régler."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT numero_facture, date_facture, montant, montant_regle, statut, operation_constat_id "
        "FROM factures WHERE tiers_id = ? ORDER BY date_facture DESC, id DESC"
    )
    query.addBindValue(tiers_id)
    query.exec()
    lignes = []
    while query.next():
        montant, montant_regle = query.value(2), query.value(3)
        lignes.append(
            {
                "numero_facture": query.value(0),
                "date_facture": query.value(1),
                "montant": montant,
                "montant_regle": montant_regle,
                "solde": round(montant - montant_regle, 2),
                "statut": query.value(4),
                "comptabilisee": bool(query.value(5)),
            }
        )
    return lignes


def reglements_tiers(db: QSqlDatabase, tiers_id: int) -> list[dict]:
    """Toutes les opérations de règlement de ce tiers. Identifiées par
    operations_comptables.tiers_id (pas seulement par le numéro de compte
    collectif : celui-ci est souvent partagé par convention entre plusieurs
    tiers du même type, donc insuffisant à lui seul pour les distinguer) et
    par une écriture au DEBIT de ce compte -- le règlement le débite
    toujours, seule la constatation de la dette le crédite."""
    query = QSqlQuery(db)
    query.prepare(
        "SELECT o.date, o.libelle, e.montant, o.mode_paiement, o.banque_operateur, "
        "o.numero_compte, o.reference_paiement "
        "FROM operations_comptables o "
        "JOIN ecritures_comptables e ON e.operation_id = o.id "
        "JOIN plan_tiers t ON t.id = o.tiers_id "
        "WHERE o.tiers_id = ? AND e.sens = 'DEBIT' AND e.compte = t.compte_collectif "
        "ORDER BY o.date DESC, o.id DESC"
    )
    query.addBindValue(tiers_id)
    query.exec()
    lignes = []
    while query.next():
        mode_paiement = query.value(3) or None
        lignes.append(
            {
                "date": query.value(0),
                "libelle": query.value(1),
                "montant": query.value(2),
                "mode_paiement": mode_paiement,
                "mode_paiement_libelle": MODE_PAIEMENT_LABELS.get(mode_paiement, mode_paiement or "—"),
                "banque_operateur": query.value(4) or None,
                "numero_compte": query.value(5) or None,
                "reference_paiement": query.value(6) or None,
            }
        )
    return lignes


def charger_releve(db: QSqlDatabase, tiers_id: int) -> ReleveTiers | None:
    infos = charger_infos_tiers(db, tiers_id)
    if infos is None:
        return None
    factures = factures_tiers(db, tiers_id)
    solde_du = round(sum(f["solde"] for f in factures if f["comptabilisee"]), 2)
    return ReleveTiers(
        infos=infos,
        factures=factures,
        reglements=reglements_tiers(db, tiers_id),
        solde_du=solde_du,
    )


def _localisation(infos: InfosTiers) -> str:
    parties = [p for p in (infos.localite, infos.departement, infos.region) if p]
    return ", ".join(parties) if parties else "—"


def _libelle_type(infos: InfosTiers) -> str:
    """« Prestataire » plutôt que « Fournisseur » dans le titre du relevé,
    pour les tiers de type FOURNISSEUR classifiés en prestataire de santé
    (toute classification autre que la générique « Fournisseur », ex.
    pharmacie, hôpital, poste de santé…)."""
    if infos.type == "FOURNISSEUR" and infos.classification != "Fournisseur":
        return "Prestataire"
    return infos.type


def releve_html(releve: ReleveTiers) -> str:
    infos = releve.infos
    lignes_factures = "".join(
        f"<tr><td>{f['numero_facture']}</td><td>{f['date_facture']}</td>"
        f"<td style='text-align:right'>{formater_montant(f['montant'])}</td>"
        f"<td style='text-align:right'>{formater_montant(f['montant_regle'])}</td>"
        f"<td style='text-align:right'>{formater_montant(f['solde'])}</td>"
        f"<td>{STATUT_LABELS.get(f['statut'], f['statut'])}</td></tr>"
        for f in releve.factures
    ) or "<tr><td colspan='6'><i>Aucune facture</i></td></tr>"

    lignes_reglements = "".join(
        f"<tr><td>{r['date']}</td><td>{r['libelle']}</td>"
        f"<td style='text-align:right'>{formater_montant(r['montant'])}</td>"
        f"<td>{r['mode_paiement_libelle']}</td>"
        f"<td>{r['banque_operateur'] or '—'}</td>"
        f"<td>{r['numero_compte'] or '—'}</td>"
        f"<td>{r['reference_paiement'] or '—'}</td></tr>"
        for r in releve.reglements
    ) or "<tr><td colspan='7'><i>Aucun règlement</i></td></tr>"

    return f"""
    <html>
    <head><style>
        body {{ font-family: sans-serif; font-size: 11pt; }}
        h1 {{ font-size: 16pt; margin-bottom: 0; }}
        h2 {{ font-size: 13pt; margin-top: 24px; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 6px; }}
        th, td {{ border: 1px solid #999; padding: 2px 5px; font-size: 8pt; white-space: nowrap; }}
        th {{ background: #eee; text-align: left; }}
        .infos p {{ margin: 2px 0; }}
        .solde {{ font-size: 12pt; font-weight: bold; margin-top: 16px; }}
    </style></head>
    <body>
        <h1>Relevé de tiers</h1>
        <div class="infos">
            <p><b>{infos.numero} — {infos.intitule}</b> ({_libelle_type(infos)})</p>
            <p>Adresse : {infos.adresse or "—"}</p>
            <p>Téléphone : {infos.telephone or "—"} — Email : {infos.email or "—"}</p>
            <p>Classification : {infos.classification or "—"} — Localisation : {_localisation(infos)}</p>
            <p>Compte collectif : {infos.compte_collectif}</p>
        </div>

        <h2>Factures</h2>
        <table>
            <tr><th>N° facture</th><th>Date</th><th>Montant</th><th>Réglé</th><th>Solde</th><th>Statut</th></tr>
            {lignes_factures}
        </table>

        <h2>Règlements</h2>
        <table>
            <tr><th>Date</th><th>Libellé</th><th>Montant</th><th>Mode</th>
                <th>Banque/opérateur</th><th>N° compte</th><th>Référence</th></tr>
            {lignes_reglements}
        </table>

        <p class="solde">Solde dû : {formater_montant(releve.solde_du)}</p>
    </body>
    </html>
    """


def imprimer_releve_pdf(releve: ReleveTiers, chemin: Path) -> None:
    document = QTextDocument()
    document.setHtml(releve_html(releve))

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(chemin))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(10, 15, 10, 15), QPageLayout.Unit.Millimeter)

    document.setPageSize(printer.pageRect(QPrinter.Unit.Point).size())
    document.print_(printer)
