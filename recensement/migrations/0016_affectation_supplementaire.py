# Migration 0016 — Affectations supplémentaires multi-zones pour agents
#
# Permet à un agent recenseur d'intervenir dans plusieurs zones,
# chacune attribuée par un utilisateur habilité et tracée individuellement.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recensement', '0015_ficheparoisse_code_officiel_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AffectationSupplementaire',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('role_attributeur', models.CharField(
                    blank=True, max_length=20,
                    help_text="Rôle de l'utilisateur au moment de l'attribution.",
                )),
                ('date_attribution', models.DateTimeField(auto_now_add=True)),
                ('statut', models.CharField(
                    choices=[
                        ('active', 'Active'),
                        ('suspendue', 'Suspendue'),
                        ('revoquee', 'Révoquée'),
                        ('expiree', 'Expirée'),
                    ],
                    default='active',
                    max_length=15,
                )),
                ('date_fin', models.DateTimeField(
                    blank=True, null=True,
                    help_text='Date de suspension, révocation ou expiration.',
                )),
                ('motif', models.TextField(
                    blank=True,
                    help_text="Commentaire ou justification de l'affectation.",
                )),
                ('agent', models.ForeignKey(
                    help_text='Agent recenseur concerné.',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='affectations_supplementaires',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('attribue_par', models.ForeignKey(
                    help_text="Utilisateur ayant accordé cette affectation.",
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='affectations_accordees',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('region', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='recensement.region',
                )),
                ('province', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='recensement.province',
                )),
                ('district', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='recensement.district',
                )),
                ('zone', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='affectations',
                    to='recensement.zone',
                )),
            ],
            options={
                'verbose_name': 'Affectation supplémentaire',
                'verbose_name_plural': 'Affectations supplémentaires',
                'ordering': ['-date_attribution'],
            },
        ),
        migrations.AddConstraint(
            model_name='affectationsupplementaire',
            constraint=models.UniqueConstraint(
                condition=models.Q(('statut', 'active')),
                fields=('agent', 'zone'),
                name='unique_affectation_active_agent_zone',
            ),
        ),
    ]
