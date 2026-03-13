# Bot Orchestrator

## Phase 1 — Manual (current)

After a user completes onboarding, a `bot_instances` row is created with `status = 'pending_start'`. Anton sees pending bots in the admin panel and manually starts a Docker container on the VPS for each user.

**No code runs here.** The orchestrator is a null stub.

## Phase 2 — Automatic (future)

When ready to automate bot startup:

1. Implement the `BotOrchestrator` interface in `index.ts`
2. Options: Docker API, Kubernetes, or serverless
3. **Only `index.ts` changes** — `types.ts` and all consumers remain stable

## Files

- `types.ts` — Interfaces: `BotOrchestrator`, `BotConfig`, `BotStatus`
- `index.ts` — Exports types + `botOrchestrator = null` (stub)
