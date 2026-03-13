"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  Rocket,
  Link2,
  Settings,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Eye,
  EyeOff,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ALLOWED_COINS, TIERS } from "@/lib/constants";
import { ALL_EXCHANGES, type ExchangeId, type ExchangeProvider } from "@/lib/exchanges";
import type { Tier } from "@/types";

interface OnboardingWizardProps {
  tier: string;
  email: string;
}

const STEPS = [
  { label: "Welcome", icon: Rocket },
  { label: "Exchange", icon: Link2 },
  { label: "Bot Setup", icon: Settings },
  { label: "Complete", icon: CheckCircle2 },
];

const COIN_LABELS: Record<string, string> = {
  BTCUSD: "BTC/USD",
  ETHUSD: "ETH/USD",
  SOLUSD: "SOL/USD",
  AVAXUSD: "AVAX/USD",
  LINKUSD: "LINK/USD",
  LTCUSD: "LTC/USD",
};

function ProgressBar({ currentStep }: { currentStep: number }) {
  return (
    <div className="w-full mb-8">
      <div className="flex items-center justify-between relative">
        <div className="absolute top-5 left-0 right-0 h-0.5 bg-border" />
        <div
          className="absolute top-5 left-0 h-0.5 bg-accent transition-all duration-500 ease-out"
          style={{
            width: `${(currentStep / (STEPS.length - 1)) * 100}%`,
          }}
        />

        {STEPS.map((step, index) => {
          const Icon = step.icon;
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;

          return (
            <div
              key={step.label}
              className="flex flex-col items-center relative z-10"
            >
              <div
                className={`
                  w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300
                  ${
                    isCompleted
                      ? "bg-accent text-white"
                      : isCurrent
                      ? "bg-accent text-white ring-4 ring-accent/20"
                      : "bg-bg-card border border-border text-text-muted"
                  }
                `}
              >
                {isCompleted ? (
                  <Check className="w-5 h-5" />
                ) : (
                  <Icon className="w-5 h-5" />
                )}
              </div>
              <span
                className={`
                  mt-2 text-xs font-medium transition-colors duration-300
                  ${isCurrent || isCompleted ? "text-text-primary" : "text-text-muted"}
                `}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Step 1: Welcome ─────────────────────────────────────────────
function StepWelcome({
  tier,
  onNext,
}: {
  tier: string;
  onNext: () => void;
}) {
  const tierKey = (tier as Tier) || "starter";
  const tierInfo = TIERS[tierKey] || TIERS.starter;

  return (
    <div className="text-center space-y-6">
      <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center mx-auto">
        <Rocket className="w-8 h-8 text-accent" />
      </div>

      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-text-primary">
          Welcome to CryptoBot!
        </h2>
        <p className="text-text-secondary max-w-md mx-auto">
          Let&apos;s set up your trading bot in just a few steps. You&apos;ll
          connect your exchange, configure your first bot, and be ready to trade.
        </p>
      </div>

      <div className="inline-flex items-center gap-2">
        <span className="text-sm text-text-muted">Your plan:</span>
        <Badge variant="default">{tierInfo.name}</Badge>
      </div>

      <div className="bg-bg-secondary rounded-lg p-4 max-w-sm mx-auto">
        <p className="text-xs text-text-muted mb-2 font-medium uppercase tracking-wider">
          Included features
        </p>
        <ul className="space-y-1.5">
          {tierInfo.features.map((feature) => (
            <li
              key={feature}
              className="flex items-center gap-2 text-sm text-text-secondary"
            >
              <Check className="w-4 h-4 text-success flex-shrink-0" />
              {feature}
            </li>
          ))}
        </ul>
      </div>

      <Button size="lg" onClick={onNext}>
        Let&apos;s go
      </Button>
    </div>
  );
}

// ── Step 2: Connect Exchange ────────────────────────────────────
function StepExchange({
  email,
  onNext,
  onBack,
  exchangeAccountId,
  setExchangeAccountId,
  selectedExchange,
  setSelectedExchange,
}: {
  email: string;
  onNext: () => void;
  onBack: () => void;
  exchangeAccountId: string | null;
  setExchangeAccountId: (id: string) => void;
  selectedExchange: ExchangeId;
  setSelectedExchange: (id: ExchangeId) => void;
}) {
  const [environment, setEnvironment] = useState<"demo" | "live">("demo");
  const [credentials, setCredentials] = useState<Record<string, string>>({
    identifier: email,
  });
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [verifying, setVerifying] = useState(false);
  const [saving, setSaving] = useState(false);
  const [verified, setVerified] = useState(false);
  const [saved, setSaved] = useState(!!exchangeAccountId);
  const [error, setError] = useState("");

  const exchange = ALL_EXCHANGES.find((e) => e.id === selectedExchange)!;
  const isActive = exchange.status === "active";

  const canVerify =
    isActive &&
    exchange.credentialFields.every(
      (f) => (credentials[f.key] || "").trim() !== ""
    );

  function handleExchangeSelect(ex: ExchangeProvider) {
    setSelectedExchange(ex.id);
    setVerified(false);
    setSaved(false);
    setError("");
    // Keep identifier if switching
    setCredentials({ identifier: email });
  }

  function updateCredential(key: string, value: string) {
    setCredentials((prev) => ({ ...prev, [key]: value }));
    setVerified(false);
    setSaved(false);
  }

  async function handleVerify() {
    setVerifying(true);
    setError("");
    setVerified(false);

    try {
      const res = await fetch("/api/exchange/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exchange: selectedExchange,
          environment,
          credentials,
        }),
      });

      const data = await res.json();

      if (!res.ok || data.error) {
        setError(data.error || "Verification failed. Please check your credentials.");
        return;
      }

      setVerified(true);
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setVerifying(false);
    }
  }

  async function handleSaveAndContinue() {
    setSaving(true);
    setError("");

    try {
      const res = await fetch("/api/exchange/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exchange: selectedExchange,
          environment,
          credentials,
        }),
      });

      const data = await res.json();

      if (!res.ok || data.error) {
        setError(data.error || "Failed to save credentials.");
        return;
      }

      setExchangeAccountId(data.id);
      setSaved(true);
      onNext();
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold text-text-primary">
          Connect Your Exchange
        </h2>
        <p className="text-text-secondary">
          Select your exchange and enter your API credentials.
        </p>
      </div>

      {/* Exchange picker grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {ALL_EXCHANGES.map((ex) => {
          const isSelected = ex.id === selectedExchange;
          const isComingSoon = ex.status === "coming_soon";

          return (
            <button
              key={ex.id}
              type="button"
              disabled={isComingSoon}
              onClick={() => handleExchangeSelect(ex)}
              className={`
                relative flex flex-col items-center gap-2 p-4 rounded-lg border transition-all
                ${
                  isSelected
                    ? "border-accent bg-accent-muted ring-1 ring-accent"
                    : isComingSoon
                    ? "border-border bg-bg-secondary opacity-60 cursor-not-allowed"
                    : "border-border bg-bg-secondary hover:border-border-hover"
                }
              `}
            >
              {isComingSoon && (
                <Badge
                  variant="outline"
                  className="absolute -top-2 -right-2 text-[10px] px-1.5 py-0.5"
                >
                  Soon
                </Badge>
              )}
              <Image
                src={ex.logo}
                alt={ex.name}
                width={32}
                height={32}
                className="rounded"
              />
              <span
                className={`text-xs font-medium ${
                  isSelected ? "text-accent" : "text-text-secondary"
                }`}
              >
                {ex.name}
              </span>
            </button>
          );
        })}
      </div>

      {/* Environment selector — only if exchange supports it */}
      {isActive && exchange.hasEnvironments && (
        <div className="space-y-2">
          <label className="text-sm font-medium text-text-primary">
            Environment
          </label>
          <div className="flex gap-3">
            {(["demo", "live"] as const).map((env) => (
              <button
                key={env}
                type="button"
                onClick={() => {
                  setEnvironment(env);
                  setVerified(false);
                  setSaved(false);
                }}
                className={`
                  flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all border
                  ${
                    environment === env
                      ? "bg-accent text-white border-accent"
                      : "bg-bg-secondary text-text-secondary border-border hover:border-border-hover"
                  }
                `}
              >
                {env === "demo" ? "Demo" : "Live"}
              </button>
            ))}
          </div>
          {environment === "live" && (
            <p className="text-xs text-warning">
              Live mode trades with real money. Make sure you understand the risks.
            </p>
          )}
        </div>
      )}

      {/* Dynamic credential fields */}
      {isActive &&
        exchange.credentialFields.map((field) => (
          <div key={field.key} className="space-y-2">
            <label className="text-sm font-medium text-text-primary">
              {field.label}
            </label>
            {field.type === "password" ? (
              <div className="relative">
                <Input
                  type={showSecrets[field.key] ? "text" : "password"}
                  value={credentials[field.key] || ""}
                  onChange={(e) => updateCredential(field.key, e.target.value)}
                  placeholder={field.placeholder}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() =>
                    setShowSecrets((prev) => ({
                      ...prev,
                      [field.key]: !prev[field.key],
                    }))
                  }
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
                >
                  {showSecrets[field.key] ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
            ) : (
              <Input
                value={credentials[field.key] || ""}
                onChange={(e) => updateCredential(field.key, e.target.value)}
                placeholder={field.placeholder}
              />
            )}
          </div>
        ))}

      {/* Error message */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-danger-muted text-danger text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Success message */}
      {verified && !saved && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-success-muted text-success text-sm">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          Connection verified successfully!
        </div>
      )}

      {/* Buttons */}
      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>

        {!verified ? (
          <Button
            className="flex-1"
            onClick={handleVerify}
            disabled={!canVerify || verifying}
          >
            {verifying ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Verifying...
              </>
            ) : (
              "Test Connection"
            )}
          </Button>
        ) : (
          <Button
            className="flex-1"
            onClick={handleSaveAndContinue}
            disabled={saving}
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Next"
            )}
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Step 3: Configure Bot ───────────────────────────────────────
function StepBotConfig({
  tier,
  onNext,
  onBack,
  botConfig,
  setBotConfig,
}: {
  tier: string;
  onNext: () => void;
  onBack: () => void;
  botConfig: BotConfig;
  setBotConfig: (config: BotConfig) => void;
}) {
  const tierKey = (tier as Tier) || "starter";
  const maxCoins = tierKey === "starter" ? 3 : 6;
  const defaultMaxPositions = tierKey === "starter" ? 2 : tierKey === "pro" ? 3 : 5;

  const [name, setName] = useState(botConfig.name);
  const [selectedCoins, setSelectedCoins] = useState<string[]>(botConfig.coins);
  const [riskPercent, setRiskPercent] = useState(botConfig.riskPercent);
  const [maxPositions, setMaxPositions] = useState(
    botConfig.maxPositions || defaultMaxPositions
  );

  function toggleCoin(coin: string) {
    setSelectedCoins((prev) => {
      if (prev.includes(coin)) {
        return prev.filter((c) => c !== coin);
      }
      if (prev.length >= maxCoins) return prev;
      return [...prev, coin];
    });
  }

  function handleNext() {
    setBotConfig({
      name: name.trim() || "My CryptoBot",
      coins: selectedCoins,
      riskPercent,
      maxPositions,
    });
    onNext();
  }

  const canProceed = selectedCoins.length > 0 && name.trim() !== "";

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold text-text-primary">
          Configure Your Bot
        </h2>
        <p className="text-text-secondary">
          Set up your trading preferences and select which coins to trade.
        </p>
      </div>

      {/* Bot Name */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-text-primary">
          Bot Name
        </label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My CryptoBot"
        />
      </div>

      {/* Coin Selection */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-text-primary">
            Coin Pairs
          </label>
          <span className="text-xs text-text-muted">
            {selectedCoins.length}/{maxCoins} selected
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {ALLOWED_COINS.map((coin) => {
            const isSelected = selectedCoins.includes(coin);
            const isDisabled =
              !isSelected && selectedCoins.length >= maxCoins;

            return (
              <button
                key={coin}
                type="button"
                onClick={() => toggleCoin(coin)}
                disabled={isDisabled}
                className={`
                  py-2.5 px-3 rounded-lg text-sm font-medium transition-all border
                  ${
                    isSelected
                      ? "bg-accent text-white border-accent"
                      : isDisabled
                      ? "bg-bg-secondary text-text-muted border-border opacity-50 cursor-not-allowed"
                      : "bg-bg-secondary text-text-secondary border-border hover:border-border-hover"
                  }
                `}
              >
                {COIN_LABELS[coin] || coin}
              </button>
            );
          })}
        </div>
        {tierKey === "starter" && (
          <p className="text-xs text-text-muted">
            Starter plan allows up to 3 coin pairs.{" "}
            <span className="text-accent">Upgrade to Pro</span> for all 6.
          </p>
        )}
      </div>

      {/* Risk Per Trade */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-text-primary">
            Risk Per Trade
          </label>
          <span className="text-sm font-medium text-accent">
            {riskPercent.toFixed(1)}%
          </span>
        </div>
        <input
          type="range"
          min="0.5"
          max="2.0"
          step="0.1"
          value={riskPercent}
          onChange={(e) => setRiskPercent(parseFloat(e.target.value))}
          className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-accent bg-bg-secondary"
        />
        <div className="flex justify-between text-xs text-text-muted">
          <span>0.5% (Conservative)</span>
          <span>2.0% (Aggressive)</span>
        </div>
      </div>

      {/* Max Positions */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-text-primary">
          Max Simultaneous Positions
        </label>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setMaxPositions(n)}
              className={`
                flex-1 py-2.5 rounded-lg text-sm font-medium transition-all border
                ${
                  maxPositions === n
                    ? "bg-accent text-white border-accent"
                    : "bg-bg-secondary text-text-secondary border-border hover:border-border-hover"
                }
              `}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
        <Button className="flex-1" onClick={handleNext} disabled={!canProceed}>
          Next
        </Button>
      </div>
    </div>
  );
}

// ── Step 4: Complete ────────────────────────────────────────────
function StepComplete({
  botConfig,
  exchangeAccountId,
  selectedExchange,
}: {
  botConfig: BotConfig;
  exchangeAccountId: string | null;
  selectedExchange: ExchangeId;
}) {
  const router = useRouter();
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState("");

  const exchange = ALL_EXCHANGES.find((e) => e.id === selectedExchange);

  async function handleComplete() {
    setCompleting(true);
    setError("");

    try {
      const res = await fetch("/api/onboarding/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          botName: botConfig.name,
          coins: botConfig.coins,
          riskPercent: botConfig.riskPercent,
          maxPositions: botConfig.maxPositions,
          exchangeAccountId,
        }),
      });

      const data = await res.json();

      if (!res.ok || data.error) {
        setError(data.error || "Failed to complete onboarding.");
        return;
      }

      router.push("/dashboard");
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setCompleting(false);
    }
  }

  return (
    <div className="text-center space-y-6">
      <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto">
        <CheckCircle2 className="w-8 h-8 text-success" />
      </div>

      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-text-primary">
          You&apos;re all set!
        </h2>
        <p className="text-text-secondary">
          Your trading bot is configured and ready to go.
        </p>
      </div>

      <div className="bg-bg-secondary rounded-lg p-4 max-w-sm mx-auto text-left space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-muted">Exchange</span>
          <div className="flex items-center gap-2">
            {exchange && (
              <Image
                src={exchange.logo}
                alt={exchange.name}
                width={16}
                height={16}
                className="rounded"
              />
            )}
            <Badge variant="success">{exchange?.name || "Connected"}</Badge>
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-muted">Bot name</span>
          <span className="text-sm font-medium text-text-primary">
            {botConfig.name}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-muted">Coins</span>
          <span className="text-sm font-medium text-text-primary">
            {botConfig.coins.length} selected
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-muted">Risk per trade</span>
          <span className="text-sm font-medium text-text-primary">
            {botConfig.riskPercent.toFixed(1)}%
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-muted">Max positions</span>
          <span className="text-sm font-medium text-text-primary">
            {botConfig.maxPositions}
          </span>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-danger-muted text-danger text-sm justify-center">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <Button size="lg" onClick={handleComplete} disabled={completing}>
        {completing ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Finishing up...
          </>
        ) : (
          "Go to Dashboard"
        )}
      </Button>
    </div>
  );
}

// ── Types ───────────────────────────────────────────────────────
interface BotConfig {
  name: string;
  coins: string[];
  riskPercent: number;
  maxPositions: number;
}

// ── Main Wizard ─────────────────────────────────────────────────
export function OnboardingWizard({ tier, email }: OnboardingWizardProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [exchangeAccountId, setExchangeAccountId] = useState<string | null>(
    null
  );
  const [selectedExchange, setSelectedExchange] = useState<ExchangeId>("capital_com");
  const [botConfig, setBotConfig] = useState<BotConfig>({
    name: "My CryptoBot",
    coins: ["BTCUSD", "ETHUSD"],
    riskPercent: 1.5,
    maxPositions: 2,
  });

  function goNext() {
    setCurrentStep((prev) => Math.min(prev + 1, STEPS.length - 1));
  }

  function goBack() {
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  }

  return (
    <Card className="w-full max-w-lg">
      <CardContent className="p-6 sm:p-8">
        <ProgressBar currentStep={currentStep} />

        <div className="min-h-[400px] flex flex-col justify-center">
          {currentStep === 0 && <StepWelcome tier={tier} onNext={goNext} />}

          {currentStep === 1 && (
            <StepExchange
              email={email}
              onNext={goNext}
              onBack={goBack}
              exchangeAccountId={exchangeAccountId}
              setExchangeAccountId={setExchangeAccountId}
              selectedExchange={selectedExchange}
              setSelectedExchange={setSelectedExchange}
            />
          )}

          {currentStep === 2 && (
            <StepBotConfig
              tier={tier}
              onNext={goNext}
              onBack={goBack}
              botConfig={botConfig}
              setBotConfig={setBotConfig}
            />
          )}

          {currentStep === 3 && (
            <StepComplete
              botConfig={botConfig}
              exchangeAccountId={exchangeAccountId}
              selectedExchange={selectedExchange}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
