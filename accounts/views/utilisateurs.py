"""
Gestion des comptes utilisateurs — réservée au super admin (miroir de
recensement.views utilisateur_* côté templates). Remplace l'admin Django
par défaut pour cette tâche, exactement comme la page "Utilisateurs" du
site actuel.
"""

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import EstSuperAdmin
from accounts.serializers import (
    ReinitialiserMotDePasseSerializer, UtilisateurCourantSerializer,
    UtilisateurCreationSerializer, UtilisateurUpdateSerializer,
)


class UtilisateurListView(generics.ListAPIView):
    serializer_class = UtilisateurCourantSerializer
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def get_queryset(self):
        return User.objects.select_related(
            "profil", "profil__province", "profil__district"
        ).order_by("username")


class UtilisateurDetailView(generics.RetrieveAPIView):
    serializer_class = UtilisateurCourantSerializer
    permission_classes = [IsAuthenticated, EstSuperAdmin]
    queryset = User.objects.select_related("profil", "profil__province", "profil__district")


class UtilisateurCreateView(generics.CreateAPIView):
    serializer_class = UtilisateurCreationSerializer
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = serializer.save()
        detail = UtilisateurCourantSerializer(utilisateur)
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)


class UtilisateurUpdateView(APIView):
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def put(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        serializer = UtilisateurUpdateSerializer(utilisateur, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UtilisateurCourantSerializer(utilisateur).data, status=status.HTTP_200_OK)


class UtilisateurResetPasswordView(APIView):
    """Réinitialisation de mot de passe — le super admin fixe un nouveau
    mot de passe sans connaître l'ancien (miroir de TailwindSetPasswordForm)."""

    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def post(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        serializer = ReinitialiserMotDePasseSerializer(
            data=request.data, context={"utilisateur": utilisateur},
        )
        serializer.is_valid(raise_exception=True)
        utilisateur.set_password(serializer.validated_data["new_password1"])
        utilisateur.save()
        return Response(
            {"detail": f"Mot de passe réinitialisé pour « {utilisateur.get_username()} »."},
            status=status.HTTP_200_OK,
        )


class UtilisateurToggleActifView(APIView):
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def post(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        if utilisateur == request.user:
            return Response(
                {"detail": "Vous ne pouvez pas désactiver votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        utilisateur.is_active = not utilisateur.is_active
        utilisateur.save()
        etat = "réactivé" if utilisateur.is_active else "désactivé"
        return Response(
            {"detail": f"Compte « {utilisateur.get_username()} » {etat}.", "is_active": utilisateur.is_active},
            status=status.HTTP_200_OK,
        )


class UtilisateurDeleteView(APIView):
    permission_classes = [IsAuthenticated, EstSuperAdmin]

    def delete(self, request, pk):
        utilisateur = get_object_or_404(User, pk=pk)
        if utilisateur == request.user:
            return Response(
                {"detail": "Vous ne pouvez pas supprimer votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        nom = utilisateur.get_username()
        utilisateur.delete()
        return Response(
            {"detail": f"Le compte « {nom} » a été supprimé définitivement."},
            status=status.HTTP_200_OK,
        )
