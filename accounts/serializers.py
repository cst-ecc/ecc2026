from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from recensement.models import District, Profil, Province

from .selectors import get_role


class UtilisateurCourantSerializer(serializers.ModelSerializer):
    """Profil d'un compte tel qu'exposé au frontend : rôle effectif
    (calculé, pas juste le champ brut de Profil — is_superuser prime, voir
    accounts.selectors.get_role) et périmètre éventuel. Utilisé à la fois
    pour /api/auth/me/ (la personne connectée) et pour la gestion des
    comptes par le super admin (liste/détail) — même représentation."""

    role = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    province = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "is_active",
            "role", "role_display", "province", "district",
        ]

    def get_role(self, obj):
        return get_role(obj)

    def get_role_display(self, obj):
        role = get_role(obj)
        return dict(Profil.Role.choices).get(role, role)

    def get_province(self, obj):
        profil = getattr(obj, "profil", None)
        if profil and profil.province_id:
            return {"id": profil.province_id, "nom": profil.province.nom}
        return None

    def get_district(self, obj):
        profil = getattr(obj, "profil", None)
        if profil and profil.district_id:
            return {"id": profil.district_id, "nom": profil.district.nom}
        return None


def _valider_perimetre_role(attrs):
    """Un manager doit avoir une province, un superviseur un district —
    même règle que ProfilForm.clean() côté templates."""
    role = attrs.get("role")
    erreurs = {}
    if role == Profil.Role.MANAGER and not attrs.get("province"):
        erreurs["province"] = "Une province est requise pour le rôle Manager."
    if role == Profil.Role.SUPERVISEUR and not attrs.get("district"):
        erreurs["district"] = "Un district est requis pour le rôle Superviseur."
    if erreurs:
        raise serializers.ValidationError(erreurs)


class UtilisateurCreationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, label="Mot de passe")
    password2 = serializers.CharField(write_only=True, required=True, label="Confirmation du mot de passe")
    role = serializers.ChoiceField(choices=Profil.Role.choices, required=True)
    province = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(), required=False, allow_null=True,
    )
    district = serializers.PrimaryKeyRelatedField(
        queryset=District.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "password", "password2", "role", "province", "district"]

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Cet identifiant est déjà utilisé.")
        return value

    def validate(self, attrs):
        if attrs.get("password") != attrs.pop("password2", None):
            raise serializers.ValidationError({"password2": "Les mots de passe ne correspondent pas."})
        try:
            validate_password(attrs["password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        _valider_perimetre_role(attrs)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.pop("role")
        province = validated_data.pop("province", None)
        district = validated_data.pop("district", None)

        utilisateur = User.objects.create_user(
            username=validated_data["username"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            password=password,
        )
        # Le signal post_save (recensement/models.py) a déjà créé un Profil
        # par défaut (rôle Agent) ; on applique ici les valeurs choisies.
        profil = utilisateur.profil
        profil.role = role
        profil.province = province
        profil.district = district
        profil.save()
        return utilisateur


class UtilisateurUpdateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=Profil.Role.choices, required=True)
    province = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(), required=False, allow_null=True,
    )
    district = serializers.PrimaryKeyRelatedField(
        queryset=District.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "is_active", "role", "province", "district"]

    def validate(self, attrs):
        _valider_perimetre_role(attrs)
        return attrs

    def update(self, instance, validated_data):
        role = validated_data.pop("role")
        province = validated_data.pop("province", None)
        district = validated_data.pop("district", None)

        instance.first_name = validated_data.get("first_name", instance.first_name)
        instance.last_name = validated_data.get("last_name", instance.last_name)
        instance.is_active = validated_data.get("is_active", instance.is_active)
        instance.save()

        profil, _ = Profil.objects.get_or_create(user=instance)
        profil.role = role
        profil.province = province
        profil.district = district
        profil.save()
        return instance


class ReinitialiserMotDePasseSerializer(serializers.Serializer):
    """Même principe que TailwindSetPasswordForm côté templates (basé sur
    SetPasswordForm de Django) : le super admin fixe un nouveau mot de
    passe sans connaître l'ancien, toujours passé par les validateurs
    Django standards (AUTH_PASSWORD_VALIDATORS)."""

    new_password1 = serializers.CharField(write_only=True, required=True, label="Nouveau mot de passe")
    new_password2 = serializers.CharField(write_only=True, required=True, label="Confirmation")

    def validate(self, attrs):
        if attrs["new_password1"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "Les mots de passe ne correspondent pas."})
        try:
            validate_password(attrs["new_password1"], user=self.context.get("utilisateur"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password1": list(exc.messages)})
        return attrs
