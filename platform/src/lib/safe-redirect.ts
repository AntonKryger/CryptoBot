/**
 * Sanitize redirect paths to prevent open redirect attacks.
 * Only allows relative paths starting with / (no protocol-relative // or absolute URLs).
 */
export function safeRedirect(to: string, fallback = "/dashboard"): string {
  if (!to || !to.startsWith("/") || to.startsWith("//")) {
    return fallback;
  }
  // Block any URL with a protocol
  try {
    const url = new URL(to, "http://localhost");
    if (url.host !== "localhost") return fallback;
  } catch {
    return fallback;
  }
  return to;
}
