# Generated manually for the CST ECC modular administration update.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("recensement", "0039_seed_organisations_administratives"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RolePlateforme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(editable=False, help_text="Code technique stable généré depuis le nom du rôle global.", max_length=90, unique=True)),
                ("nom", models.CharField(max_length=150, unique=True, verbose_name="Nom du rôle")),
                ("description", models.TextField(blank=True)),
                ("est_actif", models.BooleanField(db_index=True, default=True)),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                ("cree_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="roles_plateforme_crees", to=settings.AUTH_USER_MODEL)),
                ("modifie_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="roles_plateforme_modifies", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Rôle global de plateforme",
                "verbose_name_plural": "Rôles globaux de plateforme",
                "ordering": ["nom"],
            },
        ),
        migrations.CreateModel(
            name="PermissionRolePlateforme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_slug", models.SlugField(max_length=80)),
                ("submodule_slug", models.SlugField(blank=True, max_length=100)),
                ("peut_consulter", models.BooleanField(default=True)),
                ("peut_creer", models.BooleanField(default=False)),
                ("peut_modifier", models.BooleanField(default=False)),
                ("peut_supprimer", models.BooleanField(default=False)),
                ("peut_archiver", models.BooleanField(default=False)),
                ("peut_exporter", models.BooleanField(default=False)),
                ("peut_valider", models.BooleanField(default=False)),
                ("peut_administrer", models.BooleanField(default=False)),
                ("peut_telecharger", models.BooleanField(default=False)),
                ("peut_publier", models.BooleanField(default=False)),
                ("peut_gerer_qrcode", models.BooleanField(default=False)),
                ("peut_gerer_acces", models.BooleanField(default=False)),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permissions", to="recensement.roleplateforme")),
            ],
            options={
                "verbose_name": "Permission de rôle global",
                "verbose_name_plural": "Permissions de rôles globaux",
                "ordering": ["role__nom", "module_slug", "submodule_slug"],
            },
        ),
        migrations.CreateModel(
            name="RoleUtilisateurPlateforme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("statut", models.CharField(choices=[("active", "Active"), ("suspendue", "Suspendue"), ("revoquee", "Révoquée")], db_index=True, default="active", max_length=15)),
                ("date_attribution", models.DateTimeField(auto_now_add=True)),
                ("date_modification", models.DateTimeField(auto_now=True)),
                ("date_fin", models.DateTimeField(blank=True, null=True)),
                ("motif", models.TextField(blank=True)),
                ("attribue_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="roles_plateforme_attribues", to=settings.AUTH_USER_MODEL)),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attributions_utilisateurs", to="recensement.roleplateforme")),
                ("utilisateur", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="roles_plateforme", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Rôle global attribué",
                "verbose_name_plural": "Rôles globaux attribués",
                "ordering": ["utilisateur__username", "role__nom"],
            },
        ),
        migrations.CreateModel(
            name="HistoriqueRolePlateforme",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("creation_role", "Création du rôle"), ("modification_role", "Modification du rôle"), ("activation_role", "Activation du rôle"), ("desactivation_role", "Désactivation du rôle"), ("modification_permissions", "Modification des permissions"), ("attribution_utilisateur", "Attribution à un utilisateur"), ("retrait_utilisateur", "Retrait à un utilisateur")], db_index=True, max_length=40)),
                ("donnees_avant", models.JSONField(blank=True, default=dict)),
                ("donnees_apres", models.JSONField(blank=True, default=dict)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("commentaire", models.TextField(blank=True)),
                ("date_action", models.DateTimeField(auto_now_add=True)),
                ("effectue_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historiques_roles_plateforme_effectues", to=settings.AUTH_USER_MODEL)),
                ("role", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historique", to="recensement.roleplateforme")),
                ("utilisateur_cible", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historiques_roles_plateforme_cible", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Historique de rôle global",
                "verbose_name_plural": "Historiques de rôles globaux",
                "ordering": ["-date_action", "-id"],
            },
        ),
        migrations.AddIndex(model_name="roleplateforme", index=models.Index(fields=["est_actif", "nom"], name="rolepf_actif_nom_idx")),
        migrations.AddIndex(model_name="permissionroleplateforme", index=models.Index(fields=["role", "module_slug"], name="roleperm_role_mod_idx")),
        migrations.AddIndex(model_name="permissionroleplateforme", index=models.Index(fields=["module_slug", "submodule_slug"], name="roleperm_cible_idx")),
        migrations.AddConstraint(model_name="permissionroleplateforme", constraint=models.UniqueConstraint(fields=("role", "module_slug", "submodule_slug"), name="unique_perm_role_cible")),
        migrations.AddIndex(model_name="roleutilisateurplateforme", index=models.Index(fields=["utilisateur", "statut"], name="roleuser_user_statut_idx")),
        migrations.AddIndex(model_name="roleutilisateurplateforme", index=models.Index(fields=["role", "statut"], name="roleuser_role_statut_idx")),
        migrations.AddConstraint(model_name="roleutilisateurplateforme", constraint=models.UniqueConstraint(condition=models.Q(statut="active"), fields=("utilisateur", "role"), name="unique_role_user_actif")),
        migrations.AddIndex(model_name="historiqueroleplateforme", index=models.Index(fields=["action", "date_action"], name="hist_rolepf_action_idx")),
    ]
