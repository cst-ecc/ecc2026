"""Services d'e-mail liés à la création des comptes utilisateurs."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.shortcuts import resolve_url
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from ..models import HistoriqueCreationUtilisateurEmail, NotificationInterne


TYPE_NOTIFICATION_CREATION_UTILISATEUR = "creation_utilisateur"


def _email_valide(email):
    email = (email or "").strip()
    if not email:
        return False
    try:
        validate_email(email)
    except ValidationError:
        return False
    return True


def _url_absolue(request, chemin_ou_url):
    valeur = (chemin_ou_url or "").strip()
    if not valeur:
        return ""
    if valeur.startswith(("http://", "https://")):
        return valeur

    site_url = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if site_url:
        if not valeur.startswith("/"):
            valeur = f"/{valeur}"
        return f"{site_url}{valeur}"

    if request is not None:
        return request.build_absolute_uri(valeur)

    return valeur


def _url_connexion(request=None):
    login_url = getattr(settings, "LOGIN_URL", "") or "/"
    try:
        login_url = resolve_url(login_url)
    except Exception:
        login_url = str(login_url)
    return _url_absolue(request, login_url)


def _nom_affichable(user):
    return user.get_full_name() or user.get_username()


def _tracer_envoi(*, utilisateur, cree_par, email, statut, motif=""):
    return HistoriqueCreationUtilisateurEmail.objects.create(
        utilisateur=utilisateur,
        cree_par=cree_par,
        email_utilise=(email or "").strip(),
        statut=statut,
        motif=(motif or "").strip(),
    )


def _notifier_createur(*, utilisateur, cree_par, statut, motif=""):
    if cree_par is None:
        return None

    libelle_statut = {
        HistoriqueCreationUtilisateurEmail.Statut.ENVOYE: "E-mail d'accès envoyé",
        HistoriqueCreationUtilisateurEmail.Statut.NON_ENVOYE: "E-mail d'accès non envoyé",
        HistoriqueCreationUtilisateurEmail.Statut.ECHEC: "Échec d'envoi de l'e-mail d'accès",
    }.get(statut, "Statut d'e-mail d'accès")

    message = f"Le compte « {utilisateur.get_username()} » a été créé. {libelle_statut}."
    if motif:
        message = f"{message} Motif : {motif}"

    try:
        url_cible = reverse("recensement:utilisateur_update", kwargs={"pk": utilisateur.pk})
    except Exception:
        url_cible = ""

    return NotificationInterne.objects.create(
        destinataire=cree_par,
        titre=libelle_statut,
        message=message,
        type_notification=TYPE_NOTIFICATION_CREATION_UTILISATEUR,
        niveau="utilisateur",
        url_cible=url_cible,
        cree_par=cree_par,
    )


def envoyer_email_creation_utilisateur(*, utilisateur, mot_de_passe_provisoire, cree_par=None, request=None):
    """Envoie l'e-mail d'accès au compte nouvellement créé.

    Retourne un dictionnaire simple exploitable par la vue et le template.
    L'échec d'envoi ne doit jamais annuler la création du compte.
    """
    email = (getattr(utilisateur, "email", "") or "").strip().lower()

    if not _email_valide(email):
        statut = HistoriqueCreationUtilisateurEmail.Statut.NON_ENVOYE
        motif = "Aucune adresse e-mail valide renseignée pour cet utilisateur."
        _tracer_envoi(
            utilisateur=utilisateur,
            cree_par=cree_par,
            email=email,
            statut=statut,
            motif=motif,
        )
        _notifier_createur(
            utilisateur=utilisateur,
            cree_par=cree_par,
            statut=statut,
            motif=motif,
        )
        return {"statut": statut, "motif": motif, "email": email}

    inclure_mdp = bool(getattr(settings, "ENVOYER_MDP_PROVISOIRE_PAR_EMAIL", True))
    url_connexion = _url_connexion(request)

    sujet = "Votre compte a été créé — Recensement des paroisses"
    contexte = {
        "email_title": sujet,
        "preheader": "Vos informations d'accès à la plateforme de recensement des paroisses.",
        "project_name": "Recensement des paroisses",
        "platform_name": getattr(settings, "PLATFORM_NAME", "Plateforme ECC"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", ""),
        "now": timezone.now(),
        "utilisateur": utilisateur,
        "nom_utilisateur": _nom_affichable(utilisateur),
        "role": utilisateur.profil.get_role_display() if hasattr(utilisateur, "profil") else "—",
        "perimetre": utilisateur.profil.perimetre_display() if hasattr(utilisateur, "profil") else "—",
        "identifiant": utilisateur.get_username(),
        "mot_de_passe_provisoire": mot_de_passe_provisoire if inclure_mdp else "",
        "mot_de_passe_envoye": inclure_mdp,
        "action_url": url_connexion,
        "action_label": "Accéder à la plateforme",
    }

    message_html = render_to_string(
        "recensement/emails/user_created_email.html",
        contexte,
        request=request,
    )

    message_texte = (
        f"Bonjour {contexte['nom_utilisateur']},\n\n"
        "Votre compte a été créé sur la plateforme de recensement des paroisses.\n\n"
        f"Identifiant : {contexte['identifiant']}\n"
        f"Rôle : {contexte['role']}\n"
        f"Périmètre : {contexte['perimetre']}\n"
    )

    if inclure_mdp and mot_de_passe_provisoire:
        message_texte += f"Mot de passe provisoire : {mot_de_passe_provisoire}\n"
    else:
        message_texte += (
            "Le mot de passe provisoire ne figure pas dans cet e-mail. "
            "Il doit vous être transmis par un canal sécurisé ou réinitialisé par votre responsable.\n"
        )

    if url_connexion:
        message_texte += f"\nLien vers la plateforme : {url_connexion}\n"

    message_texte += "\nMerci de modifier votre mot de passe lors de votre première connexion, si cette option est disponible."

    try:
        email_message = EmailMultiAlternatives(
            subject=sujet,
            body=message_texte,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[email],
        )
        email_message.attach_alternative(message_html, "text/html")
        resultat = email_message.send(fail_silently=False)

        if resultat == 1:
            statut = HistoriqueCreationUtilisateurEmail.Statut.ENVOYE
            motif = ""
        else:
            statut = HistoriqueCreationUtilisateurEmail.Statut.ECHEC
            motif = "Le serveur SMTP n'a pas confirmé l'envoi."

    except Exception as exc:
        statut = HistoriqueCreationUtilisateurEmail.Statut.ECHEC
        motif = str(exc)

    _tracer_envoi(
        utilisateur=utilisateur,
        cree_par=cree_par,
        email=email,
        statut=statut,
        motif=motif,
    )
    _notifier_createur(
        utilisateur=utilisateur,
        cree_par=cree_par,
        statut=statut,
        motif=motif,
    )

    return {"statut": statut, "motif": motif, "email": email}
