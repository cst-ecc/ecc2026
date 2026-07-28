from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from ..models import FicheParoisse
from ..services.services_qrcode import generer_qrcode_png


def _fiche_publique(code_court):
    return get_object_or_404(
        FicheParoisse.objects.select_related(
            "region",
            "province",
            "district",
            "zone",
            "village",
        ),
        code_court__iexact=code_court,
        statut_validation=FicheParoisse.StatutValidation.VALIDEE,
        code_officiel__isnull=False,
    )


@require_GET
def paroisse_verifier(request, code_court):
    fiche = _fiche_publique(code_court)

    return render(
        request,
        "recensement/paroisse_verification.html",
        {
            "fiche": fiche,
        },
    )


@require_GET
def paroisse_qrcode(request, code_court):
    fiche = _fiche_publique(code_court)

    url_verification = request.build_absolute_uri(
        reverse(
            "recensement:paroisse_verifier",
            kwargs={"code_court": fiche.code_court},
        )
    )

    image_png = generer_qrcode_png(url_verification)

    response = HttpResponse(
        image_png,
        content_type="image/png",
    )

    response["Cache-Control"] = "public, max-age=86400"
    response["Content-Disposition"] = (
        f'inline; filename="qrcode-{fiche.code_court}.png"'
    )

    return response

