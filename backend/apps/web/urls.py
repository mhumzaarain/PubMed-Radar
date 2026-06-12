from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import EmailAuthenticationForm
from .throttling import rate_limit

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path(
        "login/",
        rate_limit("login", limit=20)(
            auth_views.LoginView.as_view(
                authentication_form=EmailAuthenticationForm,
                redirect_authenticated_user=True,
            )
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "register/",
        rate_limit("register", limit=10)(views.RegisterView.as_view()),
        name="register",
    ),
]
