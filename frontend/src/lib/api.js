// API client. The base URL comes from (in order): runtime config written by the
// Docker container, the build-time VITE_API_BASE_URL, or localhost in dev only.
// A production build never silently falls back to localhost.

function resolveBaseUrl() {
  const runtime = window.__LYFTR_CONFIG__?.apiBaseUrl;
  const buildTime = import.meta.env.VITE_API_BASE_URL;
  const value = runtime || buildTime || (import.meta.env.DEV ? "http://localhost:8000" : "");
  return value.replace(/\/+$/, "");
}

export const API_BASE_URL = resolveBaseUrl();

export class ApiError extends Error {
  constructor(kind, message, status) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

function describeValidation(detail) {
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    const field = Array.isArray(first.loc) ? first.loc.filter((p) => p !== "body").join(".") : "";
    const msg = String(first.msg || "invalid input").replace(/^Value error, /, "");
    return field ? `${field}: ${msg}` : msg;
  }
  return typeof detail === "string" ? detail : "The request was invalid.";
}

async function request(path, options = {}) {
  if (!API_BASE_URL) {
    throw new ApiError("config", "The backend URL is not configured for this deployment.");
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, options);
  } catch {
    throw new ApiError("network", "Can't reach the Lyftr AI backend. Check your connection and try again.");
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (response.ok) return body;

  const detail = body?.detail;
  if (response.status === 422) {
    throw new ApiError("validation", `Message not accepted — ${describeValidation(detail)}.`, 422);
  }
  if (response.status === 503) {
    throw new ApiError(
      "unavailable",
      detail === "all providers unavailable"
        ? "All AI providers are unavailable right now (every key in the pool failed). Please try again shortly."
        : "The service is temporarily unavailable. Please try again shortly.",
      503,
    );
  }
  throw new ApiError("unexpected", `Something went wrong (HTTP ${response.status}). Please try again.`, response.status);
}

export function sendChat({ sessionId, message, systemPrompt, simulateFailure }) {
  const headers = { "Content-Type": "application/json" };
  if (simulateFailure) headers["X-Simulate-Failure"] = simulateFailure;
  const payload = { session_id: sessionId, message };
  if (systemPrompt && systemPrompt.trim()) payload.system_prompt = systemPrompt.trim();
  return request("/chat", { method: "POST", headers, body: JSON.stringify(payload) });
}

export function getHealth(signal) {
  return request("/health", { signal });
}
