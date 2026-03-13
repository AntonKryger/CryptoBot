export function verifySyncSecret(request: Request): boolean {
  const secret = request.headers.get("X-Sync-Secret");
  return secret === process.env.SYNC_SECRET;
}
