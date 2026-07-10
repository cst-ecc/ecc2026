from django.urls import path

from . import views

app_name = "parishes"

urlpatterns = [
    path("", views.ParishListView.as_view(), name="list"),
    path("<int:pk>/", views.ParishDetailView.as_view(), name="detail"),
]
