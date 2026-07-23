"""Helpers de rendu des e-mails HTML / texte.

Ce module ne modifie pas la logique métier d'envoi.
Il centralise uniquement la génération du sujet, de la version texte et de la
version HTML des e-mails, afin d'éviter de coder le HTML directement dans les
services de relance ou de notification.
"""

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone


def _nom_utilisateur(user):
    if not user:
        return "Utilisateur"
    return user.get_full_name() or user.get_username()


def _role_utilisateur(user):
    profil = getattr(user, "profil", None)
    if profil and hasattr(profil, "get_role_display"):
        return profil.get_role_display()
    return "—"


def _perimetre_utilisateur(user):
    profil = getattr(user, "profil", None)
    if profil and hasattr(profil, "perimetre_display"):
        return profil.perimetre_display()
    return "—"


def _absolute_url(path):
    site_url = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not path:
        return site_url or ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{site_url}{path}" if site_url else path


def contexte_base_email(**kwargs):
    """Contexte commun à tous les e-mails."""
    contexte = {
        "platform_name": "Plateforme ECC",
        "project_name": "Recensement des paroisses",
        "site_url": (getattr(settings, "SITE_URL", "") or "").rstrip("/"),
        "support_email": getattr(settings, "SERVER_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", ""),
        "now": timezone.localtime(timezone.now()),
    }
    contexte.update(kwargs)
    return contexte


def rendre_email_relance(
    *,
    fiche,
    destinataire,
    niveau_relance,
    effectue_par=None,
    url_cible="",
    nb_fiches_concernees=1,
):
    """Rend l'e-mail de relance en version texte et HTML.

    Retourne :
        (subject, text_body, html_body)
    """
    niveaux = {
        1: "Première relance",
        2: "Deuxième relance",
        3: "Dernière relance",
    }
    niveau_label = niveaux.get(niveau_relance, "Relance")

    action_url = _absolute_url(url_cible)

    contexte = contexte_base_email(
        email_title="Vous avez une validation en attente",
        preheader=f"{niveau_label} concernant une fiche de recensement dans votre périmètre.",
        niveau_relance=niveau_relance,
        niveau_relance_label=niveau_label,
        fiche=fiche,
        destinataire=destinataire,
        destinataire_nom=_nom_utilisateur(destinataire),
        destinataire_role=_role_utilisateur(destinataire),
        perimetre=_perimetre_utilisateur(destinataire),
        auteur=_nom_utilisateur(effectue_par) if effectue_par else "Système",
        auteur_role=_role_utilisateur(effectue_par) if effectue_par else "—",
        date_relance=timezone.localtime(timezone.now()),
        nb_fiches_concernees=nb_fiches_concernees or 1,
        action_url=action_url,
        action_label="Ouvrir la plateforme",
        message_principal=(
            "Une relance vous a été adressée concernant une fiche de recensement "
            "en attente de traitement dans votre périmètre."
        ),
        message_action=(
            "Merci de vous connecter à la plateforme afin de consulter la fiche "
            "et d'effectuer l'action attendue selon votre rôle."
        ),
    )

    subject = f"{niveau_label} — validation en attente"
    text_body = render_to_string("recensement/emails/relance_email.txt", contexte).strip()
    html_body = render_to_string("recensement/emails/relance_email.html", contexte).strip()
    return subject, text_body, html_body


def rendre_email_notification(
    *,
    titre,
    message,
    destinataire=None,
    url_cible="",
    action_label="Ouvrir la plateforme",
):
    """Template générique pour une notification importante."""
    contexte = contexte_base_email(
        email_title=titre or "Notification",
        preheader=(message or "")[:140],
        destinataire=destinataire,
        destinataire_nom=_nom_utilisateur(destinataire),
        message_principal=message or "",
        action_url=_absolute_url(url_cible),
        action_label=action_label,
    )

    subject = titre or "Notification — Plateforme ECC"
    text_body = render_to_string("recensement/emails/notification_email.txt", contexte).strip()
    html_body = render_to_string("recensement/emails/notification_email.html", contexte).strip()
    return subject, text_body, html_body
