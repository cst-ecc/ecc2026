# Generated manually for CST ECC — Administration > Employés

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0037_alter_gradeecclesial_categorie"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganisationAdministrative",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=200, unique=True, verbose_name="Nom de l'organisation")),
                ("sigle", models.CharField(help_text="Utilisé dans le matricule des employés. Exemple : CSMO, CST, ECC.", max_length=20, unique=True, verbose_name="Sigle")),
                ("type_organisation", models.CharField(choices=[("csmo", "Conseil Supérieur de Mise en œuvre"), ("cst", "Conseil Supérieur de Transition"), ("ecc", "Église du Christianisme Céleste"), ("diocese", "Diocèse"), ("commission", "Commission"), ("departement", "Département"), ("autre", "Autre structure")], db_index=True, default="autre", max_length=30, verbose_name="Type d'organisation")),
                ("description", models.TextField(blank=True)),
                ("est_active", models.BooleanField(db_index=True, default=True)),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                ("cree_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="organisations_administratives_creees", to=settings.AUTH_USER_MODEL)),
                ("modifie_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="organisations_administratives_modifiees", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Organisation administrative",
                "verbose_name_plural": "Organisations administratives",
                "ordering": ["nom"],
            },
        ),
        migrations.CreateModel(
            name="Employe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("matricule", models.CharField(db_index=True, editable=False, help_text="Matricule généré automatiquement au format YYYYSIGLEXXXXX, sans tiret.", max_length=40, unique=True)),
                ("nom", models.CharField(max_length=120, verbose_name="Nom")),
                ("prenoms", models.CharField(blank=True, max_length=180, verbose_name="Prénoms")),
                ("fonction", models.CharField(max_length=200, verbose_name="Fonction")),
                ("date_debut_service", models.DateField(verbose_name="Date de début de service")),
                ("date_fin_service", models.DateField(blank=True, null=True, verbose_name="Date de fin de service")),
                ("statut", models.CharField(choices=[("actif", "Actif"), ("inactif", "Inactif"), ("suspendu", "Suspendu"), ("fin_service", "Fin de service"), ("archive", "Archivé")], db_index=True, default="actif", max_length=20)),
                ("telephone", models.CharField(blank=True, max_length=30, verbose_name="Téléphone")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="Adresse e-mail")),
                ("photo", models.ImageField(blank=True, null=True, upload_to="employes/photos/%Y/%m/", verbose_name="Photo")),
                ("observations", models.TextField(blank=True)),
                ("acces_plateforme", models.BooleanField(default=False, help_text="Indique si l'employé est autorisé à disposer d'un accès applicatif.", verbose_name="Autoriser l'accès à la plateforme")),
                ("acces_modules_snapshot", models.JSONField(blank=True, default=list, help_text="Instantané des modules/sous-modules autorisés au moment de l'enregistrement.")),
                ("dernier_email_acces_statut", models.CharField(blank=True, max_length=20)),
                ("dernier_email_acces_motif", models.TextField(blank=True)),
                ("dernier_email_acces_adresse", models.EmailField(blank=True, max_length=254)),
                ("dernier_email_acces_date", models.DateTimeField(blank=True, null=True)),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                ("cree_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employes_crees", to=settings.AUTH_USER_MODEL)),
                ("modifie_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employes_modifies", to=settings.AUTH_USER_MODEL)),
                ("organisation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="employes", to="recensement.organisationadministrative", verbose_name="Organisation")),
                ("utilisateur", models.OneToOneField(blank=True, help_text="Lien facultatif : un employé peut exister sans compte utilisateur.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fiche_employe", to=settings.AUTH_USER_MODEL, verbose_name="Compte utilisateur lié")),
            ],
            options={
                "verbose_name": "Employé",
                "verbose_name_plural": "Employés",
                "ordering": ["nom", "prenoms", "matricule"],
            },
        ),
        migrations.CreateModel(
            name="AccesModuleUtilisateur",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_slug", models.SlugField(max_length=80)),
                ("submodule_slug", models.SlugField(blank=True, max_length=100)),
                ("statut", models.CharField(choices=[("active", "Active"), ("suspendue", "Suspendue"), ("revoquee", "Révoquée")], db_index=True, default="active", max_length=15)),
                ("peut_consulter", models.BooleanField(default=True)),
                ("peut_creer", models.BooleanField(default=False)),
                ("peut_modifier", models.BooleanField(default=False)),
                ("peut_administrer", models.BooleanField(default=False)),
                ("date_attribution", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                ("date_fin", models.DateTimeField(blank=True, null=True)),
                ("motif", models.TextField(blank=True)),
                ("attribue_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="acces_modules_attribues", to=settings.AUTH_USER_MODEL)),
                ("utilisateur", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="acces_modules_plateforme", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Accès modulaire utilisateur",
                "verbose_name_plural": "Accès modulaires utilisateurs",
                "ordering": ["utilisateur__username", "module_slug", "submodule_slug"],
            },
        ),
        migrations.CreateModel(
            name="HistoriqueEmploye",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("creation", "Création"), ("modification", "Modification"), ("changement_statut", "Changement de statut"), ("liaison_utilisateur", "Liaison à un utilisateur"), ("creation_utilisateur", "Création du compte utilisateur"), ("modification_acces", "Modification des accès modulaires"), ("email_acces_envoye", "E-mail d'accès envoyé"), ("email_acces_non_envoye", "E-mail d'accès non envoyé"), ("email_acces_echec", "Échec d'envoi d'e-mail d'accès"), ("qr_code", "Consultation ou génération QR code"), ("archivage", "Archivage")], db_index=True, max_length=40)),
                ("donnees_avant", models.JSONField(blank=True, default=dict)),
                ("donnees_apres", models.JSONField(blank=True, default=dict)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("commentaire", models.TextField(blank=True)),
                ("date_action", models.DateTimeField(auto_now_add=True)),
                ("effectue_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historiques_employes_effectues", to=settings.AUTH_USER_MODEL)),
                ("employe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historique", to="recensement.employe")),
            ],
            options={
                "verbose_name": "Historique employé",
                "verbose_name_plural": "Historiques employés",
                "ordering": ["-date_action", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="organisationadministrative",
            index=models.Index(fields=["type_organisation", "est_active"], name="orgadm_type_active_idx"),
        ),
        migrations.AddIndex(
            model_name="employe",
            index=models.Index(fields=["statut", "organisation"], name="employe_statut_org_idx"),
        ),
        migrations.AddIndex(
            model_name="employe",
            index=models.Index(fields=["nom", "prenoms"], name="employe_nom_prenoms_idx"),
        ),
        migrations.AddConstraint(
            model_name="accesmoduleutilisateur",
            constraint=models.UniqueConstraint(condition=models.Q(("statut", "active")), fields=("utilisateur", "module_slug", "submodule_slug"), name="unique_acces_module_actif_user"),
        ),
        migrations.AddIndex(
            model_name="accesmoduleutilisateur",
            index=models.Index(fields=["utilisateur", "statut"], name="acces_module_user_statut_idx"),
        ),
        migrations.AddIndex(
            model_name="accesmoduleutilisateur",
            index=models.Index(fields=["module_slug", "submodule_slug"], name="acces_module_slug_idx"),
        ),
        migrations.AddIndex(
            model_name="historiqueemploye",
            index=models.Index(fields=["action", "date_action"], name="hist_employe_action_date_idx"),
        ),
    ]
