# Session Auth + Frontend Skeleton — Design

**Date:** 2026-06-11
**Status:** Approved
**Phase:** 2 of the post-restructure roadmap (Phase 1: Procrastinate + LLM pipeline, shipped on `backend-dev`)

## Context

Phase 1 left the backend with JWT auth (SimpleJWT) designed for a separate SPA that
will never exist: the project direction is Django templates + vanilla JS, same-origin.
This phase swaps JWT for Django session auth with classic server-rendered form pages,
sets up the template/static skeleton, and ends with a thin authenticated dashboard
shell that proves the whole stack (templates → session → JS → DRF with CSRF).

Decisions made during brainstorming:

- **Auth pages:** classic Django forms (built-in `LoginView`/`LogoutView`, small
  register `FormView`) — not JS-driven auth endpoints.
- **Registration:** open to anyone; rate-limited (10/hour/IP, carried over from the
  DRF throttle config).
- **Scope:** ends with a thin proof page, not a real dashboard (that is Phase 3).
- **Structure:** new `apps/web` app owns all page views/URLs; one project-level
  `backend/templates/` and `backend/static/` tree (Approach A).
- `django-cors-headers` is removed along with SimpleJWT — everything is same-origin.

## URL map

| URL | What | Access |
| --- | --- | --- |
| `/` | Dashboard shell (`apps/web`) | login required → redirects to `/login/` |
| `/login/`, `/register/` | Auth pages | anonymous |
| `/logout/` | POST-only; navbar renders it as a small form button | logged in |
| `/api/` | Existing JSON api_root, moved from `/` | session |
| `/api/radars/`, `/api/papers/` | Unchanged DRF endpoints | session |
| `/api/auth/*` | **Deleted** (register/login/logout/token-refresh) | — |

Settings: `LOGIN_URL = "/login/"`, `LOGIN_REDIRECT_URL = "/"`,
`LOGOUT_REDIRECT_URL = "/login/"`.

## Auth views (`apps/web/views.py`)

- **Login:** Django's built-in `LoginView`. The stock `AuthenticationForm` picks up
  `USERNAME_FIELD = "email"` from the custom User model, so email login works without
  a custom form. Template: `registration/login.html` (LoginView's default location).
- **Logout:** built-in `LogoutView` (POST-only in Django 5).
- **Register:** `FormView` with a `RegisterForm` (email + password + confirm
  password) calling `User.objects.create_user`; on success logs the user in
  (`django.contrib.auth.login`) and redirects to `/`. Duplicate email and password
  mismatch surface as form errors.
- **Dashboard:** `login_required` TemplateView rendering `web/dashboard.html`.

### Rate limiting

DRF throttles do not run on Django form views. The existing protection is preserved
with a small cache-based decorator in `apps/web` (roughly 15 lines, no new
dependency): register POST limited to 10/hour/IP, login POST to 20/hour/IP,
returning HTTP 429 over the limit. Uses Django's default cache (locmem is fine for
the single-process MVP).

## Settings & dependency changes

- Add `BASE_DIR`; `TEMPLATES["DIRS"] = [BASE_DIR / "templates"]`;
  `STATICFILES_DIRS = [BASE_DIR / "static"]`.
- `INSTALLED_APPS`: add `apps.web`; remove `rest_framework_simplejwt`,
  `rest_framework_simplejwt.token_blacklist`, `corsheaders`.
- `MIDDLEWARE`: remove `CorsMiddleware`.
- `REST_FRAMEWORK`: `DEFAULT_AUTHENTICATION_CLASSES` → `SessionAuthentication` only.
  DRF then enforces CSRF on unsafe API methods — the contract `api.js` is written
  against.
- Remove the `SIMPLE_JWT` block and all `CORS_*` settings.
- `pyproject.toml`: drop `djangorestframework-simplejwt` and `django-cors-headers`.
- `.env.example`: drop the JWT lifetime and CORS variables.
- **Migration ordering caveat:** run `manage.py migrate token_blacklist zero` BEFORE
  removing the app from `INSTALLED_APPS`, otherwise its tables are orphaned.

## Template & static skeleton

```text
backend/
├── templates/
│   ├── base.html                 # html shell: css link, navbar, content + scripts blocks
│   ├── registration/
│   │   ├── login.html
│   │   └── register.html
│   └── web/
│       └── dashboard.html        # thin proof page
├── static/
│   ├── css/app.css               # minimal layout/nav/form styling
│   └── js/
│       ├── api.js                # apiFetch() wrapper — the seam all future JS uses
│       └── dashboard.js          # proof-page logic
```

- **`base.html`:** navbar (app name; when authenticated: user email + POST logout
  button), `{% block content %}`, `{% block scripts %}`.
- **`js/api.js`:** single `apiFetch(url, options)` wrapper — same-origin credentials,
  reads the `csrftoken` cookie and sets `X-CSRFToken` on unsafe methods, sets
  `Accept: application/json`, parses JSON, throws on non-OK responses. Plain ES
  module, no build step.
- **`js/dashboard.js`:** on load, `apiFetch("/api/radars/")` and render radar names
  (handles DRF's paginated `{results: [...]}` shape), with empty state ("No radars
  yet") and error state. Deliberately nothing more — real dashboard UI is Phase 3.

## Deletions/changes in existing code

- `apps/users/views.py`: JWT Register/Login/Logout views deleted. The app keeps the
  model, manager, serializers (`UserSerializer` likely serves Phase 3), factories.
- `apps/users/urls.py`: deleted. `config/urls.py` drops the `api/auth/` include,
  includes `apps.web.urls` at root, moves api_root to `/api/`.
- `apps/users/throttles.py`: deleted (superseded by the cache decorator).
- `apps/users/tests/test_auth.py`: JWT flow tests deleted, replaced by `apps/web`
  page tests.
- `conftest.py`: `auth_client` fixture switches from JWT credentials to
  `client.force_authenticate(user)`; existing radar/paper API tests pass unchanged.

## Testing

`apps/web/tests/test_auth_pages.py`:

- login page renders; valid login redirects to `/`; invalid shows form error;
  21st login attempt within the hour → 429
- register creates user, auto-logs-in, redirects to `/`; duplicate email and
  password mismatch show form errors; 11th register attempt → 429
- logout POST redirects to `/login/`; GET `/logout/` rejected (405)
- `/` redirects anonymous to `/login/?next=/`; renders the dashboard template when
  logged in

`apps/web/tests/test_api_session.py` (the integration seam):

- session-logged-in client gets 200 from `GET /api/radars/`
- unsafe API method without a CSRF token → 403, using an
  `enforce_csrf_checks=True` client — locks in the CSRF contract `api.js` relies on

Throttle tests clear the cache between tests (fixture).

## Out of scope (later phases)

- Real dashboard UI, paper cards, filters, search (Phase 3 — also fills the Paper
  API filter gaps: date range, relevance, novelty, journal, full-text search)
- Exports, weekly digest, analytics (Phase 4)
