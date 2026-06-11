# Session Auth + Frontend Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace JWT auth with Django session auth (classic form pages for login/register/logout) and stand up the Django-templates + vanilla-JS frontend skeleton, ending with a thin authenticated dashboard that proves the templates → session → JS → DRF-with-CSRF stack.

**Architecture:** New `apps/web` app owns all page views/URLs; templates live in project-level `backend/templates/`, static files in `backend/static/`. SimpleJWT and django-cors-headers are removed entirely; DRF authenticates via `SessionAuthentication` only (which also enforces CSRF on unsafe API methods — the contract `js/api.js` is written against). Register/login form POSTs keep their old rate limits via a small cache-based decorator.

**Tech Stack:** Django 5.1 (contrib.auth views, templates), DRF SessionAuthentication, vanilla ES-module JS (no build step), pytest + pytest-django, uv.

**Spec:** `docs/superpowers/specs/2026-06-11-session-auth-frontend-skeleton-design.md`
**Branch:** `frontend-skeleton` (based on `backend-dev`). Do NOT commit to `main`.

**Conventions used throughout:**

- All commands run from `/workspace/backend` with `uv run`.
- `client` in tests is pytest-django's Django test client fixture; `api_client`/`auth_client` are the DRF fixtures in `backend/conftest.py`.
- **Gotcha to remember:** Django's `AuthenticationForm` names its identifier field `username` even though our `USERNAME_FIELD` is `email` — login POSTs send `{"username": <email>, "password": ...}`.
- `UserFactory` sets every user's password to `"testpass123"`.

---

### Task 1: Auth backend swap — remove JWT/CORS, switch DRF to session auth

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/config/urls.py`
- Modify: `backend/conftest.py`
- Modify: `backend/pyproject.toml`
- Modify: `/workspace/.env.example`
- Modify: `backend/apps/papers/tests/test_papers.py`, `backend/apps/radars/tests/test_radars.py`, `backend/apps/radars/tests/test_fetch_action.py` (401 → 403 only)
- Delete: `backend/apps/users/views.py`, `backend/apps/users/urls.py`, `backend/apps/users/throttles.py`, `backend/apps/users/tests/test_auth.py`

- [ ] **Step 1: Drop the token_blacklist tables while the app is still installed**

Run: `cd /workspace/backend && uv run python manage.py migrate token_blacklist zero`
Expected: its migrations unapply with `OK`. (Anyone else with an existing DB must run this before pulling these changes — note it in the eventual PR description.)

- [ ] **Step 2: Edit `backend/config/settings.py`**

Apply all of the following:

1. Add `from pathlib import Path` at the top and `BASE_DIR = Path(__file__).resolve().parent.parent` right after the imports; delete `from datetime import timedelta` (only SIMPLE_JWT used it).
1. `THIRD_PARTY_APPS` becomes:

```python
THIRD_PARTY_APPS = [
    "rest_framework",
    "procrastinate.contrib.django",
]
```

1. Remove `"corsheaders.middleware.CorsMiddleware"` from `MIDDLEWARE`.
1. In `TEMPLATES`, set `"DIRS": [BASE_DIR / "templates"]`.
1. After `STATIC_URL`, add `STATICFILES_DIRS = [BASE_DIR / "static"]`.
1. Replace the `REST_FRAMEWORK` auth classes and drop the now-unused form throttle scopes:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
```

1. Delete the entire `# --- SimpleJWT ---` block and the entire `# --- CORS ---` block.
1. Add auth redirect settings (after `AUTH_PASSWORD_VALIDATORS`):

```python
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
```

- [ ] **Step 3: Delete the JWT auth module files**

```bash
cd /workspace/backend
git rm apps/users/views.py apps/users/urls.py apps/users/throttles.py apps/users/tests/test_auth.py
```

(`apps/users` keeps `models.py`, `serializers.py`, `factories.py`, `admin.py`, `apps.py`, migrations.)

- [ ] **Step 4: Rewrite `backend/config/urls.py`**

Replace the entire file with (api_root moves to `/api/`, `api/auth/` include gone; `apps.web.urls` is included now and created in Task 2 — that's fine because nothing imports it until then, see Step 6 check):

```python
from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return Response({
        "radars": request.build_absolute_uri("/api/radars/"),
        "papers": request.build_absolute_uri("/api/papers/"),
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok"})


urlpatterns = [
    path("health/", health_check),
    path("admin/", admin.site.urls),
    path("api/", api_root),
    path("api/radars/", include("apps.radars.urls")),
    path("api/papers/", include("apps.papers.urls")),
]
```

NOTE: the `path("", include("apps.web.urls"))` line is deliberately NOT added yet — it lands in Task 2 when the app exists. Until then `/` 404s, which no remaining test asserts against.

- [ ] **Step 5: Update `backend/conftest.py`**

Remove the `from rest_framework_simplejwt.tokens import RefreshToken` import and replace the `auth_client` fixture with:

```python
@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user
```

- [ ] **Step 6: Flip unauthenticated-API assertions from 401 to 403**

SessionAuthentication returns 403 (no `WWW-Authenticate` header) for anonymous requests. Update exactly these assertions from `== 401` to `== 403`:

- `apps/papers/tests/test_papers.py` lines 104, 145, 237
- `apps/radars/tests/test_radars.py` lines 37, 91
- `apps/radars/tests/test_fetch_action.py` line 43

(Line numbers are pre-edit; match on `assert response.status_code == 401`.)

- [ ] **Step 7: Drop the dependencies**

In `backend/pyproject.toml` remove these two lines from `dependencies`:

```toml
    "djangorestframework-simplejwt==5.3.1",
    "django-cors-headers==4.6.0",
```

Run: `cd /workspace/backend && uv sync --extra dev`
Expected: both packages (and `pyjwt`) removed from the environment; `uv.lock` updated.

- [ ] **Step 8: Update `/workspace/.env.example`**

Delete the `# CORS — comma-separated list of allowed origins` block (with `CORS_ALLOWED_ORIGINS=...`) and the `# JWT` block (with both `JWT_*` lines).

- [ ] **Step 9: Verify the suite is green**

Run: `cd /workspace/backend && uv run pytest -q && uv run ruff check .`
Expected: **89 passed** (98 minus the 9 deleted JWT-flow tests in test_auth.py), ruff clean. Everything must pass; 89 is the new baseline.

- [ ] **Step 10: Commit**

```bash
cd /workspace && git add -A backend/ .env.example
git commit -m "feat!: replace JWT auth with Django session auth for DRF

Removes SimpleJWT and django-cors-headers (same-origin app), switches DRF
to SessionAuthentication, drops /api/auth/* endpoints. Run
'manage.py migrate token_blacklist zero' before deploying to an existing DB.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: apps/web — login/logout pages, base template, dashboard shell

**Files:**
- Create: `backend/apps/web/__init__.py`, `backend/apps/web/apps.py`, `backend/apps/web/views.py`, `backend/apps/web/urls.py`
- Create: `backend/templates/base.html`, `backend/templates/registration/login.html`, `backend/templates/web/dashboard.html`
- Create: `backend/static/css/app.css`
- Modify: `backend/config/settings.py` (add `apps.web`), `backend/config/urls.py` (include web urls)
- Test: `backend/apps/web/tests/__init__.py`, `backend/apps/web/tests/test_auth_pages.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/web/tests/__init__.py` (empty) and `backend/apps/web/tests/test_auth_pages.py`:

```python
import pytest

from apps.users.factories import UserFactory

LOGIN_URL = "/login/"
LOGOUT_URL = "/logout/"
DASHBOARD_URL = "/"


@pytest.mark.django_db
class TestLoginPage:
    def test_login_page_renders(self, client):
        response = client.get(LOGIN_URL)
        assert response.status_code == 200
        assert b"<form" in response.content

    def test_login_success_redirects_to_dashboard(self, client):
        user = UserFactory()
        response = client.post(
            LOGIN_URL, {"username": user.email, "password": "testpass123"}
        )
        assert response.status_code == 302
        assert response.url == DASHBOARD_URL

    def test_login_wrong_password_shows_error(self, client):
        user = UserFactory()
        response = client.post(LOGIN_URL, {"username": user.email, "password": "nope"})
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_authenticated_user_redirected_away_from_login(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(LOGIN_URL)
        assert response.status_code == 302
        assert response.url == DASHBOARD_URL


@pytest.mark.django_db
class TestLogout:
    def test_logout_post_redirects_to_login(self, client):
        client.force_login(UserFactory())
        response = client.post(LOGOUT_URL)
        assert response.status_code == 302
        assert response.url == LOGIN_URL

    def test_logout_get_not_allowed(self, client):
        client.force_login(UserFactory())
        response = client.get(LOGOUT_URL)
        assert response.status_code == 405


@pytest.mark.django_db
class TestDashboardShell:
    def test_anonymous_redirected_to_login(self, client):
        response = client.get(DASHBOARD_URL)
        assert response.status_code == 302
        assert response.url == f"{LOGIN_URL}?next=/"

    def test_renders_for_logged_in_user(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(DASHBOARD_URL)
        assert response.status_code == 200
        assert b'id="radar-list"' in response.content
        assert user.email.encode() in response.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_auth_pages.py -v`
Expected: FAIL at collection or all tests fail with 404s — `apps.web` doesn't exist yet.

- [ ] **Step 3: Create the app skeleton**

`backend/apps/web/__init__.py`: empty.

`backend/apps/web/apps.py`:

```python
from django.apps import AppConfig


class WebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.web"
```

`backend/apps/web/views.py`:

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "web/dashboard.html"
```

`backend/apps/web/urls.py`:

```python
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path(
        "login/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
```

- [ ] **Step 4: Register the app and URLs**

In `backend/config/settings.py`, add `"apps.web"` to `LOCAL_APPS`.
In `backend/config/urls.py`, append to `urlpatterns`:

```python
    path("", include("apps.web.urls")),
```

- [ ] **Step 5: Create templates and CSS**

`backend/templates/base.html`:

```html
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}PubMed Radar{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'css/app.css' %}">
</head>
<body>
  <nav class="navbar">
    <a class="brand" href="/">PubMed Radar</a>
    {% if user.is_authenticated %}
      <div class="nav-user">
        <span>{{ user.email }}</span>
        <form method="post" action="{% url 'logout' %}">
          {% csrf_token %}
          <button type="submit" class="link-button">Log out</button>
        </form>
      </div>
    {% endif %}
  </nav>
  <main class="container">
    {% block content %}{% endblock %}
  </main>
  {% block scripts %}{% endblock %}
</body>
</html>
```

`backend/templates/registration/login.html` (LoginView's default template path):

```html
{% extends "base.html" %}
{% block title %}Log in — PubMed Radar{% endblock %}
{% block content %}
<h1>Log in</h1>
<form method="post" class="auth-form">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Log in</button>
</form>
{% endblock %}
```

`backend/templates/web/dashboard.html` (JS wiring comes in Task 5):

```html
{% extends "base.html" %}
{% block title %}Dashboard — PubMed Radar{% endblock %}
{% block content %}
<h1>Your radars</h1>
<ul id="radar-list" data-empty-text="No radars yet."></ul>
{% endblock %}
```

`backend/static/css/app.css`:

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: #1a1a2e; }
.navbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.75rem 1.5rem; background: #16324f; color: #fff;
}
.navbar a.brand { color: #fff; text-decoration: none; font-weight: 700; }
.nav-user { display: flex; gap: 0.75rem; align-items: center; }
.nav-user form { margin: 0; }
.link-button {
  background: none; border: none; color: #9fc9eb; cursor: pointer;
  text-decoration: underline; font-size: 1rem; padding: 0;
}
.container { max-width: 60rem; margin: 2rem auto; padding: 0 1.5rem; }
.auth-form { max-width: 24rem; }
.auth-form label { display: block; margin-top: 0.75rem; }
.auth-form input { width: 100%; padding: 0.5rem; margin-top: 0.25rem; }
.auth-form button { margin-top: 1rem; padding: 0.5rem 1.25rem; }
.errorlist { color: #b00020; padding-left: 1rem; }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_auth_pages.py -v`
Expected: 8 tests PASS

- [ ] **Step 7: Lint, full suite, commit**

```bash
cd /workspace/backend && uv run ruff check . && uv run pytest -q
cd /workspace && git add backend/apps/web/ backend/templates/ backend/static/ backend/config/
git commit -m "feat: add apps/web with session login/logout pages and dashboard shell

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Register page

**Files:**
- Create: `backend/apps/web/forms.py`
- Modify: `backend/apps/web/views.py`, `backend/apps/web/urls.py`
- Create: `backend/templates/registration/register.html`
- Test: `backend/apps/web/tests/test_auth_pages.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/web/tests/test_auth_pages.py`. Add to the constants at the top:

```python
REGISTER_URL = "/register/"
```

Add to the imports:

```python
from django.contrib.auth import get_user_model

User = get_user_model()
```

Append the test class:

```python
@pytest.mark.django_db
class TestRegisterPage:
    def test_register_page_renders(self, client):
        response = client.get(REGISTER_URL)
        assert response.status_code == 200
        assert b"<form" in response.content

    def test_register_creates_user_logs_in_and_redirects(self, client):
        payload = {
            "email": "new@example.com",
            "password": "phase2-Secur3-pw",
            "password_confirm": "phase2-Secur3-pw",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 302
        assert response.url == DASHBOARD_URL
        assert User.objects.filter(email="new@example.com").exists()
        # auto-login: dashboard now renders instead of redirecting
        assert client.get(DASHBOARD_URL).status_code == 200

    def test_register_duplicate_email_shows_error(self, client):
        UserFactory(email="taken@example.com")
        payload = {
            "email": "taken@example.com",
            "password": "phase2-Secur3-pw",
            "password_confirm": "phase2-Secur3-pw",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 200
        assert "email" in response.context["form"].errors

    def test_register_password_mismatch_shows_error(self, client):
        payload = {
            "email": "new@example.com",
            "password": "phase2-Secur3-pw",
            "password_confirm": "different-pw-123",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 200
        assert "password_confirm" in response.context["form"].errors

    def test_register_weak_password_shows_error(self, client):
        payload = {
            "email": "new@example.com",
            "password": "12345678",
            "password_confirm": "12345678",
        }
        response = client.post(REGISTER_URL, payload)
        assert response.status_code == 200
        assert "password" in response.context["form"].errors
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_auth_pages.py::TestRegisterPage -v`
Expected: all 5 FAIL with 404 (no `/register/` route yet).

- [ ] **Step 3: Implement the form**

Create `backend/apps/web/forms.py`:

```python
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class RegisterForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Confirm password"
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if password and confirm and password != confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        if password:
            try:
                validate_password(password)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
        )
```

- [ ] **Step 4: Implement the view and route**

In `backend/apps/web/views.py`, replace the file content with:

```python
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from .forms import RegisterForm


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "web/dashboard.html"


class RegisterView(FormView):
    template_name = "registration/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return super().form_valid(form)
```

In `backend/apps/web/urls.py`, add to `urlpatterns`:

```python
    path("register/", views.RegisterView.as_view(), name="register"),
```

Create `backend/templates/registration/register.html`:

```html
{% extends "base.html" %}
{% block title %}Register — PubMed Radar{% endblock %}
{% block content %}
<h1>Create account</h1>
<form method="post" class="auth-form">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Register</button>
</form>
<p>Already have an account? <a href="{% url 'login' %}">Log in</a></p>
{% endblock %}
```

Also add the symmetric link to `backend/templates/registration/login.html`, after the form:

```html
<p>No account? <a href="{% url 'register' %}">Register</a></p>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_auth_pages.py -v`
Expected: 13 tests PASS

- [ ] **Step 6: Lint and commit**

```bash
cd /workspace/backend && uv run ruff check apps/web/
cd /workspace && git add backend/apps/web/ backend/templates/registration/
git commit -m "feat: add registration page with auto-login

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Rate limiting for login and register POSTs

**Files:**
- Create: `backend/apps/web/throttling.py`
- Modify: `backend/apps/web/urls.py`
- Test: `backend/apps/web/tests/test_auth_pages.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/web/tests/test_auth_pages.py`. Add to the imports:

```python
from django.core.cache import cache
```

Append:

```python
@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestAuthThrottling:
    def test_login_throttled_after_20_posts(self, client):
        user = UserFactory()
        for _ in range(20):
            response = client.post(
                LOGIN_URL, {"username": user.email, "password": "wrong"}
            )
            assert response.status_code == 200
        response = client.post(
            LOGIN_URL, {"username": user.email, "password": "wrong"}
        )
        assert response.status_code == 429

    def test_register_throttled_after_10_posts(self, client):
        for i in range(10):
            response = client.post(
                REGISTER_URL,
                {
                    "email": f"u{i}@example.com",
                    "password": "phase2-Secur3-pw",
                    "password_confirm": "phase2-Secur3-pw",
                },
            )
            assert response.status_code == 302
        response = client.post(
            REGISTER_URL,
            {
                "email": "u11@example.com",
                "password": "phase2-Secur3-pw",
                "password_confirm": "phase2-Secur3-pw",
            },
        )
        assert response.status_code == 429

    def test_get_requests_not_throttled(self, client):
        for _ in range(25):
            assert client.get(LOGIN_URL).status_code == 200
```

NOTE: the register test logs the client in on each successful POST (auto-login); that does not affect throttling, which is keyed on IP and method only. The `_clear_throttle_cache` autouse fixture is module-wide — it also isolates earlier test classes from these counters.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_auth_pages.py::TestAuthThrottling -v`
Expected: `test_login_throttled_after_20_posts` and `test_register_throttled_after_10_posts` FAIL (last response is 200/302, not 429); `test_get_requests_not_throttled` PASSES.

- [ ] **Step 3: Implement the decorator**

Create `backend/apps/web/throttling.py`:

```python
from django.core.cache import cache
from django.http import HttpResponse

WINDOW_SECONDS = 3600


def rate_limit(scope: str, limit: int):
    """Per-IP rate limit for form POSTs, mirroring the old DRF throttle rates.

    Counts POSTs per IP in a rolling cache window; over the limit returns 429.
    Uses the default cache (locmem) — adequate for the single-process MVP.
    """

    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if request.method == "POST":
                ip = request.META.get("REMOTE_ADDR", "unknown")
                key = f"rate-limit:{scope}:{ip}"
                count = cache.get(key, 0)
                if count >= limit:
                    return HttpResponse(
                        "Too many requests. Try again later.", status=429
                    )
                cache.set(key, count + 1, timeout=WINDOW_SECONDS)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
```

- [ ] **Step 4: Wire it into the URLs**

In `backend/apps/web/urls.py`, replace the file content with:

```python
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .throttling import rate_limit

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path(
        "login/",
        rate_limit("login", limit=20)(
            auth_views.LoginView.as_view(redirect_authenticated_user=True)
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_auth_pages.py -v`
Expected: 16 tests PASS

- [ ] **Step 6: Lint and commit**

```bash
cd /workspace/backend && uv run ruff check apps/web/
cd /workspace && git add backend/apps/web/
git commit -m "feat: rate-limit login and register form posts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: JS layer — api.js, dashboard.js, and the session/CSRF integration tests

**Files:**
- Create: `backend/static/js/api.js`, `backend/static/js/dashboard.js`
- Modify: `backend/templates/web/dashboard.html`
- Test: `backend/apps/web/tests/test_api_session.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/web/tests/test_api_session.py`:

```python
import pytest
from django.test import Client

from apps.users.factories import UserFactory

RADARS_URL = "/api/radars/"


@pytest.mark.django_db
class TestSessionApiAccess:
    def test_session_login_grants_api_access(self, client):
        client.force_login(UserFactory())
        response = client.get(RADARS_URL)
        assert response.status_code == 200

    def test_unauthenticated_api_request_rejected(self, client):
        response = client.get(RADARS_URL)
        assert response.status_code == 403

    def test_unsafe_method_without_csrf_token_rejected(self):
        # The contract js/api.js is written against: session-authed unsafe
        # requests MUST carry X-CSRFToken, or DRF's SessionAuthentication 403s.
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(UserFactory())
        response = csrf_client.post(
            RADARS_URL, {"name": "x", "pubmed_query": "cancer imaging"}
        )
        assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify current state**

Run: `cd /workspace/backend && uv run pytest apps/web/tests/test_api_session.py -v`
Expected: all 3 PASS already (they lock in Task 1's behavior — that's their job; they are regression armor for the JS contract, not new behavior). If any FAIL, Task 1 was mis-applied — stop and investigate.

- [ ] **Step 3: Create `backend/static/js/api.js`**

```javascript
const UNSAFE_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export async function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (UNSAFE_METHODS.has(method)) {
    headers.set("X-CSRFToken", getCookie("csrftoken") || "");
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }
  const response = await fetch(url, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${url}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}
```

- [ ] **Step 4: Create `backend/static/js/dashboard.js`**

```javascript
import { apiFetch } from "./api.js";

async function loadRadars() {
  const list = document.getElementById("radar-list");
  try {
    const data = await apiFetch("/api/radars/");
    const radars = data.results ?? data;
    if (radars.length === 0) {
      list.textContent = list.dataset.emptyText;
      return;
    }
    for (const radar of radars) {
      const item = document.createElement("li");
      item.textContent = radar.name;
      list.appendChild(item);
    }
  } catch (err) {
    list.textContent = "Could not load radars.";
    console.error(err);
  }
}

loadRadars();
```

- [ ] **Step 5: Wire the script into the dashboard template**

In `backend/templates/web/dashboard.html`, add `{% load static %}` after the extends line, and append at the end of the file:

```html
{% block scripts %}
<script type="module" src="{% static 'js/dashboard.js' %}"></script>
{% endblock %}
```

- [ ] **Step 6: Verify static files resolve and the page includes the script**

Run: `cd /workspace/backend && uv run python manage.py findstatic js/api.js js/dashboard.js css/app.css`
Expected: each found under `/workspace/backend/static/`.

Run: `cd /workspace/backend && uv run pytest apps/web/ -v`
Expected: 19 tests PASS (16 page tests + 3 session/CSRF tests).

- [ ] **Step 7: Commit**

```bash
cd /workspace && git add backend/static/js/ backend/templates/web/dashboard.html backend/apps/web/tests/test_api_session.py
git commit -m "feat: add apiFetch CSRF helper and dashboard proof page JS

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Final verification and manual smoke test

**Files:** none (verification only)

- [ ] **Step 1: Full suite + lint**

Run: `cd /workspace/backend && uv run pytest -q && uv run ruff check .`
Expected: all tests pass (Task 1 baseline + 19 web tests), ruff clean.

- [ ] **Step 2: Confirm no JWT/CORS remnants**

Run: `grep -rn "simplejwt\|corsheaders\|SIMPLE_JWT\|CORS_" /workspace/backend --include="*.py" | grep -v .venv`
Expected: no output.

- [ ] **Step 3: Manual smoke test (run and report; needs the dev server + DB)**

```bash
cd /workspace/backend && uv run python manage.py migrate && uv run python manage.py runserver 0.0.0.0:8000 &
```

Then verify with curl:

1. `curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost:8000/` → `302 .../login/?next=/`
1. `curl -s http://localhost:8000/login/ | grep -c "<form"` → at least 1
1. `curl -s http://localhost:8000/health/` → `{"status":"ok"}`
1. `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/radars/` → `403`
1. Kill the server.

(Full browser flow — register, see dashboard render "No radars yet." via JS — is a human step; note it as remaining manual QA in the report.)

- [ ] **Step 4: Commit anything outstanding (should be nothing) and report**

Run: `cd /workspace && git status --short` — expect clean (except the user's untracked CLAUDE.md).
