# Bot Orchestrator Reference

## Fase 1 — Manuel (nuvaerende)

Bruger gennemfoerer onboarding → config gemmes i Supabase med `bot_instances.status = 'pending_start'`.
Anton ser i `/admin` hvilke bots der venter og starter dem manuelt.

**Flow:**
1. Bruger betaler (Stripe) → `role = 'subscriber'`, tier sat
2. Bruger gennemfoerer onboarding → exchange account + bot instance oprettet
3. `bot_instances.status = 'pending_start'`
4. Anton ser pending bots i admin panel
5. Anton starter Docker container manuelt paa VPS
6. Python bot koerer, syncer status via `/api/sync/status`

## Fase 2 — Automatisk (fremtid)

Kun `services/bot-orchestrator/index.ts` aendres. Alt andet forbliver uaendret.
Mulige implementeringer:
- Docker API (spin up container per bruger)
- Kubernetes pods
- Serverless functions

## BotOrchestrator Interface

```typescript
interface BotOrchestrator {
  startBot(userId: string, config: BotConfig): Promise<void>;
  stopBot(botInstanceId: string): Promise<void>;
  getBotStatus(botInstanceId: string): Promise<BotStatus>;
  restartBot(botInstanceId: string): Promise<void>;
}
```

## BotConfig Interface

```typescript
interface BotConfig {
  userId: string;
  exchangeAccountId: string;
  botType: string;
  coins: string[];
  maxRiskPercent: number;
  maxPositions: number;
  encryptedApiKey: string;
  encryptedApiSecret: string;
  encryptionIv: string;
}
```

## BotStatus Type

```typescript
type BotStatus =
  | 'pending_start'
  | 'running'
  | 'paused'
  | 'suspended'
  | 'stopped'
  | 'error';
```

## Multi-tenant arkitektur

**Beslutning:** En Docker container per bruger-bot.

**Begrundelse:**
- Fuld isolation — en brugers crash paavirker ikke andre
- Simpel resource management
- Nem at starte/stoppe individuelt
- Ingen multi-tenant logik i Python bot kode
- Skalerer horisontalt

**Konsekvens:**
- Python bot kode kraever INGEN aendringer for multi-tenant
- Hver container faar sin egen config (user-specifik)
- Kill switch virker per container via Supabase check
