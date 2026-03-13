"use client";

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { TelegramSetup } from "@/components/dashboard/TelegramSetup";

export default function TelegramPage() {
  return (
    <DashboardLayout pageTitle="Telegram Notifications">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6">
          <h2 className="text-xl font-bold text-text-primary">
            Telegram Connection
          </h2>
          <p className="mt-1 text-sm text-text-muted">
            Connect your Telegram account to receive real-time trade
            notifications, alerts, and bot status updates.
          </p>
        </div>

        <TelegramSetup />
      </div>
    </DashboardLayout>
  );
}
