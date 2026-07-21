"""Vues d'export des fiches (prévisualisation hiérarchique + fichier Excel).

Le helper ``_fiches_export_filtrees`` est co-localisé ici car il n'est utilisé
que par les deux vues d'export. Il applique exactement les mêmes filtres et le
même tri qu'auparavant.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..models import District, FicheParoisse, Profil, Province, Region, Zone
from ..permissions import get_role, role_required
from .helpers import _fiches_visibles_pour


def _fiches_export_filtrees(request):
    fiches = _fiches_visibles_pour(request.user)
    role = get_role(request.user)

    statut_filtre = request.GET.get("statut", "")
    if role == Profil.Role.SUPER_ADMIN:
        if statut_filtre == "attente_superviseur":
            fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_SUPERVISEUR)
        elif statut_filtre == "attente_manager":
            fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.ATTENTE_MANAGER)
        elif statut_filtre == "tous":
            pass
        else:
            fiches = fiches.filter(statut_validation=FicheParoisse.StatutValidation.VALIDEE)

    def valid_id(param_name):
        value = (request.GET.get(param_name) or "").strip()
        return int(value) if value.isdigit() else None

    region_id = valid_id("region")
    province_id = valid_id("province")
    district_id = valid_id("district")
    zone_id = valid_id("zone")
    paroisse = (request.GET.get("paroisse") or "").strip()[:100]

    if region_id:
        fiches = fiches.filter(region_id=region_id)
    if province_id:
        fiches = fiches.filter(province_id=province_id)
    if district_id:
        fiches = fiches.filter(district_id=district_id)
    if zone_id:
        fiches = fiches.filter(zone_id=zone_id)
    if paroisse:
        fiches = fiches.filter(nom_paroisse__icontains=paroisse)

    return fiches.select_related("region", "province", "district", "zone", "village").order_by(
        "region__nom",
        "province__nom",
        "district__nom",
        "zone__nom",
        "nom_paroisse",
    )


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_GET
def fiche_export_preview(request):
    fiches = _fiches_export_filtrees(request)
    total = fiches.count()
    hierarchy = {}
    for fiche in fiches:
        region_nom = fiche.region.nom if fiche.region else "—"
        province_nom = fiche.province.nom if fiche.province else "—"
        district_nom = fiche.district.nom if fiche.district else "—"
        zone_nom = fiche.zone.nom if fiche.zone else "—"
        hierarchy.setdefault(region_nom, {})
        hierarchy[region_nom].setdefault(province_nom, {})
        hierarchy[region_nom][province_nom].setdefault(district_nom, {})
        hierarchy[region_nom][province_nom][district_nom].setdefault(zone_nom, [])
        hierarchy[region_nom][province_nom][district_nom][zone_nom].append(fiche)

    region = (
        Region.objects.filter(pk=request.GET.get("region")).first() if request.GET.get("region", "").isdigit() else None
    )
    province = (
        Province.objects.filter(pk=request.GET.get("province")).first()
        if request.GET.get("province", "").isdigit()
        else None
    )
    district = (
        District.objects.filter(pk=request.GET.get("district")).first()
        if request.GET.get("district", "").isdigit()
        else None
    )
    zone = Zone.objects.filter(pk=request.GET.get("zone")).first() if request.GET.get("zone", "").isdigit() else None

    filters = {
        "statut": request.GET.get("statut", ""),
        "region": region.nom if region else "",
        "province": province.nom if province else "",
        "district": district.nom if district else "",
        "zone": zone.nom if zone else "",
        "paroisse": request.GET.get("paroisse", ""),
    }

    return render(
        request,
        "recensement/fiche_export_preview.html",
        {
            "hierarchy": hierarchy,
            "total": total,
            "filters": filters,
            "query_string": request.GET.urlencode(),
        },
    )


@login_required
@role_required(Profil.Role.SUPER_ADMIN)
@require_GET
def fiche_export_excel(request):
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    fiches = _fiches_export_filtrees(request)
    wb = Workbook()
    ws = wb.active
    ws.title = "Paroisses"

    headers = ["Code officiel", "Région", "Province", "District", "Zone", "Paroisse"]
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(color="FFFFFF", bold=True)
    border = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB"),
    )

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for fiche in fiches:
        ws.append(
            [
                fiche.code_officiel or "Code officiel en attente",
                fiche.region.nom if fiche.region else "",
                fiche.province.nom if fiche.province else "",
                fiche.district.nom if fiche.district else "",
                fiche.zone.nom if fiche.zone else "",
                fiche.nom_paroisse or "",
            ]
        )

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    widths = {"A": 34, "B": 24, "C": 28, "D": 30, "E": 32, "F": 40}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    recap = wb.create_sheet("Synthèse")
    recap["A1"] = "Prévisualisation de l'export"
    recap["A1"].font = Font(bold=True, size=14)
    recap["A3"] = "Nombre de paroisses concernées"
    recap["B3"] = fiches.count()
    recap["A5"] = "Organisation des colonnes"
    recap["B5"] = "Code officiel → Région → Province → District → Zone → Paroisse"
    recap["A7"] = "Colonnes exclues"
    recap["B7"] = "Statut du bâtiment, GPS, Agent, Statut, Date, Actions"
    recap.column_dimensions["A"].width = 32
    recap.column_dimensions["B"].width = 80

    for row in recap.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="paroisses_hierarchie.xlsx"'
    return response
