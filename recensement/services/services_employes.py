"""Services du sous-module Employés."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from ..models import AccesModuleUtilisateur, HistoriqueEmploye
from ..module_registry import iter_module_access_choices, parse_access_value, serialize_access


def snapshot_employe(employe):
    """Instantané léger de la fiche employé pour l'historique."""
    if not employe:
        return {}
    return {
        "matricule": employe.matricule,
        "nom": employe.nom,
        "prenoms": employe.prenoms,
        "fonction": employe.fonction,
        "organisation_id": employe.organisation_id,
        "organisation": str(employe.organisation) if employe.organisation_id else "",
        "date_debut_service": employe.date_debut_service.isoformat() if employe.date_debut_service else None,
        "date_fin_service": employe.date_fin_service.isoformat() if employe.date_fin_service else None,
        "statut": employe.statut,
        "telephone": employe.telephone,
        "email": employe.email,
        "utilisateur_id": employe.utilisateur_id,
        "acces_plateforme": employe.acces_plateforme,
        "acces_modules_snapshot": employe.acces_modules_snapshot or [],
    }


def journaliser_employe(*, employe, action, effectue_par=None, avant=None, apres=None, details=None, commentaire=""):
    return HistoriqueEmploye.objects.create(
        employe=employe,
        action=action,
        effectue_par=effectue_par,
        donnees_avant=avant or {},
        donnees_apres=apres or {},
        details=details or {},
        commentaire=commentaire or "",
    )


def _module_label_map():
    return dict(iter_module_access_choices())


def valeurs_acces_actives(utilisateur):
    if not utilisateur:
        return []
    return [
        serialize_access(acces.module_slug, acces.submodule_slug)
        for acces in AccesModuleUtilisateur.objects.filter(
            utilisateur=utilisateur,
            statut=AccesModuleUtilisateur.Statut.ACTIVE,
        ).order_by("module_slug", "submodule_slug")
    ]


def libelles_acces_actifs(utilisateur):
    labels = _module_label_map()
    return [labels.get(value, value) for value in valeurs_acces_actives(utilisateur)]


def synchroniser_acces_modules(*, utilisateur, valeurs, attributeur=None, employe=None, motif=""):
    """Synchronise les accès modulaires actifs d'un utilisateur.

    Cette logique est volontairement séparée des rôles OP du recensement.
    """
    valeurs = set(valeurs or [])
    cibles = []
    for value in valeurs:
        parsed = parse_access_value(value)
        if parsed:
            cibles.append(parsed)

    anciens = set(valeurs_acces_actives(utilisateur)) if utilisateur else set()
    nouveaux = set(serialize_access(item["module_slug"], item.get("submodule_slug", "")) for item in cibles)

    if not utilisateur:
        return {"ajoutees": 0, "retirees": 0, "reactivees": 0, "anciens": list(anciens), "nouveaux": []}

    maintenant = timezone.now()
    ajoutees = 0
    reactivees = 0

    for item in cibles:
        acces, created = AccesModuleUtilisateur.objects.get_or_create(
            utilisateur=utilisateur,
            module_slug=item["module_slug"],
            submodule_slug=item.get("submodule_slug", ""),
            defaults={
                "statut": AccesModuleUtilisateur.Statut.ACTIVE,
                "attribue_par": attributeur,
                "motif": motif,
            },
        )
        if created:
            ajoutees += 1
        elif acces.statut != AccesModuleUtilisateur.Statut.ACTIVE:
            acces.statut = AccesModuleUtilisateur.Statut.ACTIVE
            acces.attribue_par = attributeur
            acces.date_fin = None
            acces.motif = motif
            acces.save(update_fields=["statut", "attribue_par", "date_fin", "motif", "date_modification"])
            reactivees += 1

    actifs = AccesModuleUtilisateur.objects.filter(utilisateur=utilisateur, statut=AccesModuleUtilisateur.Statut.ACTIVE)
    retirees = 0
    for acces in actifs:
        value = serialize_access(acces.module_slug, acces.submodule_slug)
        if value not in nouveaux:
            acces.statut = AccesModuleUtilisateur.Statut.REVOQUEE
            acces.date_fin = maintenant
            acces.motif = motif
            acces.save(update_fields=["statut", "date_fin", "motif", "date_modification"])
            retirees += 1

    if employe and anciens != nouveaux:
        journaliser_employe(
            employe=employe,
            action=HistoriqueEmploye.Action.MODIFICATION_ACCES,
            effectue_par=attributeur,
            avant={"acces_modules": sorted(anciens)},
            apres={"acces_modules": sorted(nouveaux)},
            commentaire=motif,
        )

    return {
        "ajoutees": ajoutees,
        "retirees": retirees,
        "reactivees": reactivees,
        "anciens": sorted(anciens),
        "nouveaux": sorted(nouveaux),
    }


def _absolute_url(request, path):
    if request is not None:
        return request.build_absolute_uri(path)
    site_url = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    return f"{site_url}{path}" if site_url else path


def _mettre_a_jour_statut_email(employe, resultat):
    employe.dernier_email_acces_statut = resultat.get("statut", "")
    employe.dernier_email_acces_motif = resultat.get("motif", "")
    employe.dernier_email_acces_adresse = resultat.get("email", "")
    employe.dernier_email_acces_date = timezone.now()
    employe.save(
        update_fields=[
            "dernier_email_acces_statut",
            "dernier_email_acces_motif",
            "dernier_email_acces_adresse",
            "dernier_email_acces_date",
            "date_modification",
        ]
    )


def envoyer_email_acces_employe(*, employe, mot_de_passe_provisoire="", effectue_par=None, request=None):
    """Envoie un e-mail d'accès employé sans bloquer la fiche en cas d'échec."""
    if not employe.email:
        resultat = {"statut": "non_envoye", "email": "", "motif": "Adresse e-mail absente."}
        _mettre_a_jour_statut_email(employe, resultat)
        journaliser_employe(
            employe=employe,
            action=HistoriqueEmploye.Action.EMAIL_ACCES_NON_ENVOYE,
            effectue_par=effectue_par,
            details=resultat,
        )
        return resultat

    if not employe.utilisateur_id:
        resultat = {"statut": "non_envoye", "email": employe.email, "motif": "Aucun compte utilisateur n'est lié."}
        _mettre_a_jour_statut_email(employe, resultat)
        journaliser_employe(
            employe=employe,
            action=HistoriqueEmploye.Action.EMAIL_ACCES_NON_ENVOYE,
            effectue_par=effectue_par,
            details=resultat,
        )
        return resultat

    login_url = _absolute_url(request, reverse("login"))
    verification_url = _absolute_url(
        request,
        reverse("recensement:employe_verifier", kwargs={"matricule": employe.matricule}),
    )
    contexte = {
        "employe": employe,
        "utilisateur": employe.utilisateur,
        "mot_de_passe_provisoire": mot_de_passe_provisoire,
        "login_url": login_url,
        "verification_url": verification_url,
        "acces_modules": libelles_acces_actifs(employe.utilisateur),
        "platform_name": "Plateforme ECC",
        "support_email": getattr(settings, "SERVER_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", ""),
    }
    subject = f"Accès à la Plateforme ECC — {employe.matricule}"
    text_body = render_to_string("recensement/emails/employe_acces_email.txt", contexte).strip()
    html_body = render_to_string("recensement/emails/employe_acces_email.html", contexte).strip()

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[employe.email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - l'échec ne doit pas annuler la fiche.
        resultat = {"statut": "echec", "email": employe.email, "motif": str(exc)}
        action = HistoriqueEmploye.Action.EMAIL_ACCES_ECHEC
    else:
        resultat = {"statut": "envoye", "email": employe.email, "motif": ""}
        action = HistoriqueEmploye.Action.EMAIL_ACCES_ENVOYE

    _mettre_a_jour_statut_email(employe, resultat)
    journaliser_employe(employe=employe, action=action, effectue_par=effectue_par, details=resultat)
    return resultat
