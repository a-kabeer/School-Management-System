from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.SmsLoginView.as_view(), name="login"),
    path("logout/", views.SmsLogoutView.as_view(), name="logout"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("password/", views.ChangePasswordView.as_view(), name="change_password"),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/new/", views.UserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", views.UserUpdateView.as_view(), name="user_update"),
    path("roles/", views.RoleListView.as_view(), name="role_list"),
    path("roles/new/", views.RoleCreateView.as_view(), name="role_create"),
    path("roles/<uuid:pk>/edit/", views.RoleUpdateView.as_view(), name="role_update"),
]
