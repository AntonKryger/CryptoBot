import { timingSafeEqual } from "crypto";

export function verifySyncSecret(request: Request): boolean {
  const secret = request.headers.get("X-Sync-Secret");
  if (!secret || !process.env.SYNC_SECRET) return false;

  const a = Buffer.from(secret);
  const b = Buffer.from(process.env.SYNC_SECRET);
  if (a.length !== b.length) return false;

  return timingSafeEqual(a, b);
}
