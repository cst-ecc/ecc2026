from django.urls import path

from . import views

app_name = "census"

urlpatterns = [
    path("", views.CensusSubmissionListView.as_view(), name="list"),
    path("<int:pk>/", views.CensusSubmissionDetailView.as_view(), name="detail"),
]
