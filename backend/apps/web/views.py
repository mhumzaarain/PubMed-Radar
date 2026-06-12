from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import FormView, TemplateView

from .forms import RegisterForm


@method_decorator(ensure_csrf_cookie, name="dispatch")
class DashboardView(LoginRequiredMixin, TemplateView):
    """ensure_csrf_cookie makes the csrftoken cookie explicit for js/api.js,
    rather than relying on the logout form in base.html rendering a token."""

    template_name = "web/dashboard.html"


class RegisterView(FormView):
    template_name = "registration/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return super().form_valid(form)
