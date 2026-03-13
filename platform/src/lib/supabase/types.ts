export type Role = "owner" | "subscriber" | "visitor";
export type Tier = "starter" | "pro" | "elite";
export type SubscriptionStatus = "none" | "active" | "past_due" | "canceled" | "grace_period";
export type BotStatus = "running" | "stopped" | "error" | "suspended";
export type TradeDirection = "BUY" | "SELL";
export type TradeStatus = "open" | "closed" | "canceled";

export interface Profile {
  id: string;
  email: string;
  full_name: string | null;
  role: Role;
  tier: Tier | null;
  has_2fa: boolean;
  onboarding_completed: boolean;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  subscription_status: SubscriptionStatus;
  grace_period_ends_at: string | null;
  theme: string;
  created_at: string;
  updated_at: string;
}

export type ExchangeId = "capital_com" | "binance" | "kraken" | "bybit" | "okx" | "coinbase";

export interface ExchangeAccount {
  id: string;
  user_id: string;
  exchange: ExchangeId;
  environment: "demo" | "live";
  credentials_encrypted: Record<string, string>;
  is_active: boolean;
  connection_verified: boolean;
  last_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BotInstance {
  id: string;
  user_id: string;
  exchange_account_id: string;
  name: string;
  status: BotStatus;
  is_suspended: boolean;
  suspended_reason: string | null;
  suspended_by: string | null;
  suspended_at: string | null;
  coins: string[];
  risk_percent: number;
  max_positions: number;
  adx_minimum: number;
  rr_minimum: number;
  last_heartbeat: string | null;
  last_signal_at: string | null;
  uptime_percent: number | null;
  created_at: string;
  updated_at: string;
}

export interface Trade {
  id: string;
  user_id: string;
  bot_instance_id: string | null;
  deal_id: string;
  deal_reference: string | null;
  epic: string;
  direction: TradeDirection;
  size: number;
  entry_price: number | null;
  exit_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  profit_loss: number | null;
  profit_loss_percent: number | null;
  status: TradeStatus;
  opened_at: string;
  closed_at: string | null;
  signal_mode: string | null;
  signal_data: Record<string, unknown> | null;
  exchange_provider: string;
  created_at: string;
  updated_at: string;
}

export interface TelegramConnection {
  id: string;
  user_id: string;
  chat_id: string | null;
  verification_code: string | null;
  code_expires_at: string | null;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

export interface PlatformStats {
  id: number;
  total_users: number;
  active_bots: number;
  total_trades: number;
  total_volume: number;
  updated_at: string;
}

export interface AuditLog {
  id: string;
  actor_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}
