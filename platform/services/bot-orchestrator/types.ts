/**
 * Bot Orchestrator — Type Definitions
 *
 * Phase 1: Manual bot startup (Anton starts bots via admin panel)
 * Phase 2: Automatic — only index.ts changes, these types stay stable
 */

export type BotStatus =
  | 'pending_start'
  | 'running'
  | 'paused'
  | 'suspended'
  | 'stopped'
  | 'error';

export interface BotConfig {
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

export interface BotOrchestrator {
  startBot(userId: string, config: BotConfig): Promise<void>;
  stopBot(botInstanceId: string): Promise<void>;
  getBotStatus(botInstanceId: string): Promise<BotStatus>;
  restartBot(botInstanceId: string): Promise<void>;
}
