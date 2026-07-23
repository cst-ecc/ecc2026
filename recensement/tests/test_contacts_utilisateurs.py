from django.contrib.auth.models import User
from django.test import TestCase

from recensement.access_forms import UtilisateurContactForm


class ContactsUtilisateursTests(TestCase):
    def test_contact_form_accepte_champs_vides(self):
        form = UtilisateurContactForm(data={"email": "", "telephone": ""})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["email"], "")
        self.assertEqual(form.cleaned_data["telephone"], "")

    def test_contact_form_refuse_email_invalide(self):
        form = UtilisateurContactForm(data={"email": "adresse-invalide", "telephone": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_contact_form_accepte_numero_beninois(self):
        form = UtilisateurContactForm(data={"email": "", "telephone": "01 96 35 56 21"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["telephone"], "0196355621")

    def test_contact_form_accepte_numero_international(self):
        form = UtilisateurContactForm(data={"email": "", "telephone": "+234 801 234 5678"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["telephone"], "+2348012345678")

    def test_user_email_et_profil_telephone_facultatifs(self):
        user = User.objects.create_user(username="AG001", password="secret")
        self.assertEqual(user.email, "")
        self.assertIsNone(user.profil.telephone)
