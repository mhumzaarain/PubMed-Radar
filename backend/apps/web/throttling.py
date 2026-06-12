import functools

from django.core.cache import cache
from django.http import HttpResponse

WINDOW_SECONDS = 3600


def rate_limit(scope: str, limit: int):
    """Per-IP rate limit for form POSTs, mirroring the old DRF throttle rates.

    Counts POSTs per IP in a rolling cache window; over the limit returns 429.
    Uses the default cache (locmem) — adequate for the single-process MVP.
    Keys on REMOTE_ADDR; revisit X-Forwarded-For if deployed behind a proxy.
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method == "POST":
                ip = request.META.get("REMOTE_ADDR", "unknown")
                key = f"rate-limit:{scope}:{ip}"
                # get-then-set is racy under concurrency (may undercount by a
                # few); acceptable fail-open margin for a single-process MVP.
                count = cache.get(key, 0)
                if count >= limit:
                    return HttpResponse(
                        "Too many requests. Try again later.",
                        status=429,
                        headers={"Retry-After": str(WINDOW_SECONDS)},
                    )
                cache.set(key, count + 1, timeout=WINDOW_SECONDS)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
