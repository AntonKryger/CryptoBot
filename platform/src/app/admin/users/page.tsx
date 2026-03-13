"use client";

import { useState, useMemo } from "react";
import { Search, Users as UsersIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
} from "@/components/ui/table";
import UserRow from "@/components/admin/UserRow";
import type { Profile, BotInstance, Trade } from "@/lib/supabase/types";

// Mock users
const mockUsers: Profile[] = [
  {
    id: "u1",
    email: "anton@cryptobot.dk",
    full_name: "Anton Kryger",
    role: "owner",
    tier: "elite",
    has_2fa: true,
    onboarding_completed: true,
    stripe_customer_id: "cus_001",
    stripe_subscription_id: "sub_001",
    subscription_status: "active",
    grace_period_ends_at: null,
    theme: "dark",
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-03-13T08:00:00Z",
  },
  {
    id: "u2",
    email: "lars@example.com",
    full_name: "Lars Nielsen",
    role: "subscriber",
    tier: "pro",
    has_2fa: true,
    onboarding_completed: true,
    stripe_customer_id: "cus_002",
    stripe_subscription_id: "sub_002",
    subscription_status: "active",
    grace_period_ends_at: null,
    theme: "dark",
    created_at: "2026-02-01T14:00:00Z",
    updated_at: "2026-03-12T18:00:00Z",
  },
  {
    id: "u3",
    email: "maria@example.com",
    full_name: "Maria Hansen",
    role: "subscriber",
    tier: "pro",
    has_2fa: false,
    onboarding_completed: true,
    stripe_customer_id: "cus_003",
    stripe_subscription_id: "sub_003",
    subscription_status: "active",
    grace_period_ends_at: null,
    theme: "dark",
    created_at: "2026-02-10T09:00:00Z",
    updated_at: "2026-03-11T12:00:00Z",
  },
  {
    id: "u4",
    email: "peter@example.com",
    full_name: "Peter Jensen",
    role: "subscriber",
    tier: "starter",
    has_2fa: true,
    onboarding_completed: true,
    stripe_customer_id: "cus_004",
    stripe_subscription_id: "sub_004",
    subscription_status: "past_due",
    grace_period_ends_at: "2026-03-20T00:00:00Z",
    theme: "dark",
    created_at: "2026-02-20T16:00:00Z",
    updated_at: "2026-03-10T10:00:00Z",
  },
  {
    id: "u5",
    email: "sophie@example.com",
    full_name: "Sophie Andersen",
    role: "subscriber",
    tier: "elite",
    has_2fa: true,
    onboarding_completed: true,
    stripe_customer_id: "cus_005",
    stripe_subscription_id: "sub_005",
    subscription_status: "active",
    grace_period_ends_at: null,
    theme: "dark",
    created_at: "2026-02-25T11:00:00Z",
    updated_at: "2026-03-13T07:00:00Z",
  },
  {
    id: "u6",
    email: "erik@example.com",
    full_name: "Erik Madsen",
    role: "visitor",
    tier: null,
    has_2fa: false,
    onboarding_completed: false,
    stripe_customer_id: null,
    stripe_subscription_id: null,
    subscription_status: "none",
    grace_period_ends_at: null,
    theme: "dark",
    created_at: "2026-03-12T20:00:00Z",
    updated_at: "2026-03-12T20:00:00Z",
  },
  {
    id: "u7",
    email: "anna@example.com",
    full_name: "Anna Pedersen",
    role: "subscriber",
    tier: "starter",
    has_2fa: false,
    onboarding_completed: true,
    stripe_customer_id: "cus_007",
    stripe_subscription_id: "sub_007",
    subscription_status: "canceled",
    grace_period_ends_at: null,
    theme: "dark",
    created_at: "2026-01-28T13:00:00Z",
    updated_at: "2026-03-08T09:00:00Z",
  },
];

const mockBots: Record<string, BotInstance[]> = {
  u1: [
    {
      id: "b1",
      user_id: "u1",
      exchange_account_id: "ea1",
      name: "BTC Scalper",
      status: "running",
      is_suspended: false,
      suspended_reason: null,
      suspended_by: null,
      suspended_at: null,
      coins: ["BTCUSD", "ETHUSD"],
      risk_percent: 1.5,
      max_positions: 3,
      adx_minimum: 20,
      rr_minimum: 2,
      last_heartbeat: new Date(Date.now() - 60000).toISOString(),
      last_signal_at: new Date(Date.now() - 300000).toISOString(),
      uptime_percent: 99.2,
      created_at: "2026-02-01T10:00:00Z",
      updated_at: "2026-03-13T08:00:00Z",
    },
  ],
  u2: [
    {
      id: "b2",
      user_id: "u2",
      exchange_account_id: "ea2",
      name: "SOL Momentum",
      status: "running",
      is_suspended: false,
      suspended_reason: null,
      suspended_by: null,
      suspended_at: null,
      coins: ["SOLUSD", "AVAXUSD"],
      risk_percent: 1.0,
      max_positions: 2,
      adx_minimum: 20,
      rr_minimum: 2,
      last_heartbeat: new Date(Date.now() - 30000).toISOString(),
      last_signal_at: null,
      uptime_percent: 97.8,
      created_at: "2026-02-10T14:00:00Z",
      updated_at: "2026-03-13T07:00:00Z",
    },
  ],
  u3: [
    {
      id: "b3",
      user_id: "u3",
      exchange_account_id: "ea3",
      name: "ETH Runner",
      status: "error",
      is_suspended: false,
      suspended_reason: null,
      suspended_by: null,
      suspended_at: null,
      coins: ["ETHUSD"],
      risk_percent: 1.5,
      max_positions: 2,
      adx_minimum: 20,
      rr_minimum: 2,
      last_heartbeat: new Date(Date.now() - 600000).toISOString(),
      last_signal_at: null,
      uptime_percent: 82.1,
      created_at: "2026-03-01T09:00:00Z",
      updated_at: "2026-03-12T22:00:00Z",
    },
  ],
  u5: [
    {
      id: "b5",
      user_id: "u5",
      exchange_account_id: "ea5",
      name: "Multi-Asset Pro",
      status: "running",
      is_suspended: false,
      suspended_reason: null,
      suspended_by: null,
      suspended_at: null,
      coins: ["BTCUSD", "ETHUSD", "SOLUSD", "LINKUSD"],
      risk_percent: 1.0,
      max_positions: 4,
      adx_minimum: 25,
      rr_minimum: 2.5,
      last_heartbeat: new Date(Date.now() - 15000).toISOString(),
      last_signal_at: new Date(Date.now() - 120000).toISOString(),
      uptime_percent: 99.9,
      created_at: "2026-03-01T11:00:00Z",
      updated_at: "2026-03-13T08:00:00Z",
    },
  ],
};

const mockTrades: Record<string, Trade[]> = {
  u1: [
    {
      id: "t1",
      user_id: "u1",
      bot_instance_id: "b1",
      deal_id: "d1",
      deal_reference: "ref1",
      epic: "BTCUSD",
      direction: "BUY",
      size: 0.5,
      entry_price: 67200,
      exit_price: 67850,
      stop_loss: 66800,
      take_profit: 68000,
      profit_loss: 325.0,
      profit_loss_percent: 2.1,
      status: "closed",
      opened_at: "2026-03-12T14:00:00Z",
      closed_at: "2026-03-12T18:00:00Z",
      signal_mode: "ai_haiku",
      signal_data: null,
      created_at: "2026-03-12T14:00:00Z",
      updated_at: "2026-03-12T18:00:00Z",
    },
  ],
  u2: [
    {
      id: "t2",
      user_id: "u2",
      bot_instance_id: "b2",
      deal_id: "d2",
      deal_reference: "ref2",
      epic: "SOLUSD",
      direction: "BUY",
      size: 10,
      entry_price: 145.5,
      exit_price: null,
      stop_loss: 140,
      take_profit: 155,
      profit_loss: null,
      profit_loss_percent: null,
      status: "open",
      opened_at: "2026-03-13T06:00:00Z",
      closed_at: null,
      signal_mode: "ema_cross",
      signal_data: null,
      created_at: "2026-03-13T06:00:00Z",
      updated_at: "2026-03-13T06:00:00Z",
    },
  ],
  u3: [],
  u5: [
    {
      id: "t3",
      user_id: "u5",
      bot_instance_id: "b5",
      deal_id: "d3",
      deal_reference: "ref3",
      epic: "ETHUSD",
      direction: "SELL",
      size: 2,
      entry_price: 3850,
      exit_price: 3780,
      stop_loss: 3900,
      take_profit: 3700,
      profit_loss: 140.0,
      profit_loss_percent: 3.6,
      status: "closed",
      opened_at: "2026-03-12T10:00:00Z",
      closed_at: "2026-03-12T16:00:00Z",
      signal_mode: "ai_haiku",
      signal_data: null,
      created_at: "2026-03-12T10:00:00Z",
      updated_at: "2026-03-12T16:00:00Z",
    },
  ],
};

export default function UsersPage() {
  const [search, setSearch] = useState("");

  const filteredUsers = useMemo(() => {
    if (!search) return mockUsers;
    const lower = search.toLowerCase();
    return mockUsers.filter(
      (u) =>
        u.email.toLowerCase().includes(lower) ||
        (u.full_name && u.full_name.toLowerCase().includes(lower))
    );
  }, [search]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <UsersIcon className="h-5 w-5 text-text-muted" />
          <h2 className="text-lg font-semibold text-text-primary">
            User Management
          </h2>
          <span className="text-sm text-text-muted">
            ({mockUsers.length} total)
          </span>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <Input
            placeholder="Search by email or name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Email</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Tier</TableHead>
              <TableHead>Subscription</TableHead>
              <TableHead>2FA</TableHead>
              <TableHead>Joined</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredUsers.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                bots={mockBots[user.id] ?? []}
                trades={mockTrades[user.id] ?? []}
              />
            ))}
            {filteredUsers.length === 0 && (
              <TableRow>
                <td
                  colSpan={8}
                  className="text-center py-8 text-text-muted text-sm"
                >
                  No users found matching &quot;{search}&quot;
                </td>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
