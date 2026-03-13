/**
 * CSRF protection: verify Origin header matches our domain.
 * Returns true if the request is safe (same-origin or allowed).
 */
export function verifyCsrf(request: Request): boolean {
  const origin = request.headers.get("origin");

  // No origin = non-browser request (curl, bot sync) — allow
  if (!origin) return true;

  // Allow requests from our own domains
  const allowed = [
    "https://platform-one-tawny.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
  ];

  // Also allow any *.vercel.app preview deployments
  if (origin.endsWith(".vercel.app")) return true;

  return allowed.includes(origin);
}
