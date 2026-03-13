/**
 * Bot Orchestrator — Stub
 *
 * Phase 1 (current): null — Anton starts bots manually via admin panel.
 *   Onboarding saves config to Supabase with status = 'pending_start'.
 *   Admin panel shows pending bots. Anton starts Docker containers on VPS.
 *
 * Phase 2 (future): Replace this stub with actual implementation.
 *   Only this file changes — types.ts and all consumers remain stable.
 */

export type { BotOrchestrator, BotConfig, BotStatus } from './types';

// Phase 1: No orchestrator — manual bot management
export const botOrchestrator = null;
