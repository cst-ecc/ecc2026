from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from recensement.models import (
    District,
    FicheParoisse,
    NiveauResponsabiliteEcclesiale,
    Profil,
    Province,
    Region,
    ResponsabiliteHierarchique,
    SiteParticulier,
    StatutBatiment,
    StatutMandatResponsableEcclesial,
    Zone,
)
from recensement.permissions import peut_gerer_responsables_ecclesiaux
from recensement.services.services_responsables_ecclesiaux import (
    construire_index_responsables,
    enregistrer_poste,
    ouvrir_mandat,
    remplacer_responsable,
    responsables_pour_fiche,
)

User = get_user_model()


class ResponsablesEcclesiauxTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_superuser("sa-test", "sa@example.com", "test")
        self.op_province = User.objects.create_user("op-province", password="test")
        self.op_province.profil.role = Profil.Role.OP_PROVINCE
        self.op_province.profil.save(update_fields=["role"])

        self.region = Region.objects.create(nom="Région Test", ordre=99, code="R99")
        self.province = Province.objects.create(region=self.region, nom="Province Test", code="P99")
        self.district = District.objects.create(province=self.province, nom="District Test", code="D99")
        self.zone = Zone.objects.create(district=self.district, nom="Zone Test", code="Z999")
        self.site = SiteParticulier.objects.create(nom="Site Test", type_site="autre")

    def creer_poste(self, niveau, **cible):
        poste = ResponsabiliteHierarchique(
            code=f"poste-{niveau}-{ResponsabiliteHierarchique.objects.count() + 1}",
            niveau=niveau,
            titre_officiel="Titre Test",
            **cible,
        )
        poste.save()
        return poste

    def test_seul_super_admin_peut_gerer(self):
        self.assertTrue(peut_gerer_responsables_ecclesiaux(self.super_admin))
        self.assertFalse(peut_gerer_responsables_ecclesiaux(self.op_province))

    def test_super_admin_peut_creer_poste_region(self):
        poste = enregistrer_poste(
            poste=ResponsabiliteHierarchique(),
            donnees={
                "niveau": NiveauResponsabiliteEcclesiale.REGION,
                "region": self.region,
                "province": None,
                "district": None,
                "zone": None,
                "site_particulier": None,
                "structure_nom": "",
                "titre_officiel": "Chef de Région",
                "titre_verrouille": False,
                "ordre": 0,
                "est_actif": True,
            },
            utilisateur=self.super_admin,
        )
        self.assertEqual(poste.region, self.region)
        self.assertEqual(poste.titre_officiel, "Chef de Région")

    def test_operateur_ne_peut_pas_creer_poste(self):
        with self.assertRaises(PermissionDenied):
            enregistrer_poste(
                poste=ResponsabiliteHierarchique(),
                donnees={
                    "niveau": NiveauResponsabiliteEcclesiale.REGION,
                    "region": self.region,
                    "titre_officiel": "Chef de Région",
                },
                utilisateur=self.op_province,
            )

    def test_poste_vacant_peut_exister_sans_nom(self):
        poste = self.creer_poste(NiveauResponsabiliteEcclesiale.REGION, region=self.region)
        mandat = ouvrir_mandat(
            poste_id=poste.pk,
            donnees={
                "nom_responsable": "",
                "contact_responsable": "",
                "date_debut": None,
                "statut": StatutMandatResponsableEcclesial.VACANT,
                "observations": "",
            },
            utilisateur=self.super_admin,
        )
        self.assertEqual(mandat.statut, StatutMandatResponsableEcclesial.VACANT)
        self.assertEqual(mandat.nom_responsable, "")

    def test_mandat_actif_exige_un_nom(self):
        poste = self.creer_poste(NiveauResponsabiliteEcclesiale.PROVINCE, province=self.province)
        with self.assertRaises(ValidationError):
            ouvrir_mandat(
                poste_id=poste.pk,
                donnees={
                    "nom_responsable": "",
                    "contact_responsable": "",
                    "date_debut": date.today(),
                    "statut": StatutMandatResponsableEcclesial.ACTIF,
                    "observations": "",
                },
                utilisateur=self.super_admin,
            )

    def test_un_seul_mandat_courant_par_poste(self):
        poste = self.creer_poste(NiveauResponsabiliteEcclesiale.DISTRICT, district=self.district)
        ouvrir_mandat(
            poste_id=poste.pk,
            donnees={
                "nom_responsable": "Premier Responsable",
                "contact_responsable": "",
                "date_debut": date(2025, 1, 1),
                "statut": StatutMandatResponsableEcclesial.ACTIF,
                "observations": "",
            },
            utilisateur=self.super_admin,
        )
        with self.assertRaises(ValidationError):
            ouvrir_mandat(
                poste_id=poste.pk,
                donnees={
                    "nom_responsable": "Deuxième Responsable",
                    "contact_responsable": "",
                    "date_debut": date(2026, 1, 1),
                    "statut": StatutMandatResponsableEcclesial.ACTIF,
                    "observations": "",
                },
                utilisateur=self.super_admin,
            )

    def test_remplacement_conserve_ancien_mandat(self):
        poste = self.creer_poste(NiveauResponsabiliteEcclesiale.ZONE, zone=self.zone)
        ancien = ouvrir_mandat(
            poste_id=poste.pk,
            donnees={
                "nom_responsable": "Ancien Responsable",
                "contact_responsable": "",
                "date_debut": date(2024, 1, 1),
                "statut": StatutMandatResponsableEcclesial.ACTIF,
                "observations": "",
            },
            utilisateur=self.super_admin,
        )
        nouveau = remplacer_responsable(
            poste_id=poste.pk,
            donnees={
                "nom_responsable": "Nouveau Responsable",
                "contact_responsable": "",
                "date_debut": date(2026, 1, 1),
                "statut": StatutMandatResponsableEcclesial.ACTIF,
                "observations": "",
            },
            motif="Fin du mandat précédent",
            utilisateur=self.super_admin,
        )
        ancien.refresh_from_db()
        self.assertEqual(ancien.statut, StatutMandatResponsableEcclesial.REMPLACE)
        self.assertEqual(ancien.date_fin, date(2026, 1, 1))
        self.assertEqual(nouveau.nom_responsable, "Nouveau Responsable")
        self.assertEqual(poste.mandats.count(), 2)

    def test_titre_site_protege(self):
        poste = self.creer_poste(
            NiveauResponsabiliteEcclesiale.SITE_PARTICULIER,
            site_particulier=self.site,
        )
        poste.titre_verrouille = True
        poste.save()
        poste.titre_officiel = "Titre modifié"
        with self.assertRaises(ValidationError):
            poste.save()

    def test_index_responsables_pour_fiche(self):
        postes = (
            self.creer_poste(NiveauResponsabiliteEcclesiale.REGION, region=self.region),
            self.creer_poste(NiveauResponsabiliteEcclesiale.PROVINCE, province=self.province),
            self.creer_poste(NiveauResponsabiliteEcclesiale.DISTRICT, district=self.district),
            self.creer_poste(NiveauResponsabiliteEcclesiale.ZONE, zone=self.zone),
        )
        for i, poste in enumerate(postes, start=1):
            ouvrir_mandat(
                poste_id=poste.pk,
                donnees={
                    "nom_responsable": f"Responsable {i}",
                    "contact_responsable": "",
                    "date_debut": date.today(),
                    "statut": StatutMandatResponsableEcclesial.ACTIF,
                    "observations": "",
                },
                utilisateur=self.super_admin,
            )
        fiche = FicheParoisse.objects.create(
            region=self.region,
            province=self.province,
            district=self.district,
            zone=self.zone,
            nom_paroisse="Paroisse Test",
            parish_shepherd="Chargé Test",
            statut_batiment=StatutBatiment.ACHEVE,
            cree_par=self.super_admin,
        )
        _, index = construire_index_responsables([fiche])
        responsables = responsables_pour_fiche(fiche, index)
        self.assertEqual(responsables["zone"]["nom"], "Responsable 4")

    def test_export_excel_contient_les_responsables(self):
        poste = self.creer_poste(NiveauResponsabiliteEcclesiale.REGION, region=self.region)
        ouvrir_mandat(
            poste_id=poste.pk,
            donnees={
                "nom_responsable": "Chef Région Test",
                "contact_responsable": "",
                "date_debut": date.today(),
                "statut": StatutMandatResponsableEcclesial.ACTIF,
                "observations": "",
            },
            utilisateur=self.super_admin,
        )
        FicheParoisse.objects.create(
            region=self.region,
            province=self.province,
            district=self.district,
            zone=self.zone,
            nom_paroisse="Paroisse Export",
            parish_shepherd="Chargé Export",
            statut_batiment=StatutBatiment.ACHEVE,
            statut_validation=FicheParoisse.StatutValidation.VALIDEE,
            cree_par=self.super_admin,
        )
        self.client.force_login(self.super_admin)
        response = self.client.get(reverse("recensement:fiche_export_excel"))
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        headers = [cell.value for cell in workbook["Paroisses"][1]]
        self.assertIn("Titre responsable région", headers)
        self.assertIn("Nom responsable zone", headers)

    def test_liste_responsables_est_paginee(self):
        for index in range(31):
            ResponsabiliteHierarchique.objects.create(
                code=f"structure-speciale-{index}",
                niveau=NiveauResponsabiliteEcclesiale.STRUCTURE_SPECIALE,
                structure_nom=f"Structure spéciale {index}",
                titre_officiel=f"Responsable spécial {index}",
            )

        self.client.force_login(self.super_admin)

        premiere_page = self.client.get(reverse("recensement:responsable_ecclesial_list"))
        self.assertEqual(premiere_page.status_code, 200)
        self.assertEqual(premiere_page.context["total"], 31)
        self.assertEqual(len(premiere_page.context["postes"]), 25)
        self.assertEqual(premiere_page.context["page_obj"].number, 1)

        deuxieme_page = self.client.get(
            reverse("recensement:responsable_ecclesial_list"),
            {"page": 2},
        )
        self.assertEqual(deuxieme_page.status_code, 200)
        self.assertEqual(len(deuxieme_page.context["postes"]), 6)
        self.assertEqual(deuxieme_page.context["page_obj"].number, 2)
