from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),

    # ID cards
    path("id-cards/student/<uuid:pk>/", views.StudentIdCardView.as_view(), name="student_card"),
    path("id-cards/staff/<uuid:pk>/", views.StaffIdCardView.as_view(), name="staff_card"),
    path("id-cards/students/", views.BulkStudentCardsView.as_view(), name="student_cards"),
    path("id-cards/staff/", views.BulkStaffCardsView.as_view(), name="staff_cards"),

    # QR target. Public by design: it shows only what the card face already
    # shows, so scanning proves the card is genuine without revealing more.
    path("verify/<str:kind>/<uuid:pk>/", views.verify_card, name="verify"),
]
