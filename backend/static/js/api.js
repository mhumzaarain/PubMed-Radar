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
