"use client";

import { useEffect, useRef, useState, memo, useMemo } from "react";
import { cn } from "@/lib/utils";

const ALL_COINS = [
  { symbol: "KRAKEN:BTCUSD", label: "BTC", name: "Bitcoin" },
  { symbol: "KRAKEN:ETHUSD", label: "ETH", name: "Ethereum" },
  { symbol: "KRAKEN:SOLUSD", label: "SOL", name: "Solana" },
  { symbol: "KRAKEN:XRPUSD", label: "XRP", name: "Ripple" },
  { symbol: "KRAKEN:ADAUSD", label: "ADA", name: "Cardano" },
  { symbol: "KRAKEN:DOGEUSD", label: "DOGE", name: "Dogecoin" },
  { symbol: "KRAKEN:AVAXUSD", label: "AVAX", name: "Avalanche" },
  { symbol: "KRAKEN:LINKUSD", label: "LINK", name: "Chainlink" },
  { symbol: "KRAKEN:DOTUSD", label: "DOT", name: "Polkadot" },
  { symbol: "KRAKEN:LTCUSD", label: "LTC", name: "Litecoin" },
  { symbol: "KRAKEN:MATICUSD", label: "MATIC", name: "Polygon" },
  { symbol: "KRAKEN:UNIUSD", label: "UNI", name: "Uniswap" },
  { symbol: "KRAKEN:ATOMUSD", label: "ATOM", name: "Cosmos" },
  { symbol: "KRAKEN:XLMUSD", label: "XLM", name: "Stellar" },
  { symbol: "KRAKEN:AAVEUSD", label: "AAVE", name: "Aave" },
  { symbol: "KRAKEN:NEARUSD", label: "NEAR", name: "NEAR Protocol" },
  { symbol: "KRAKEN:FILUSD", label: "FIL", name: "Filecoin" },
  { symbol: "KRAKEN:APTUSD", label: "APT", name: "Aptos" },
  { symbol: "KRAKEN:MKRUSD", label: "MKR", name: "Maker" },
  { symbol: "KRAKEN:GRTUSD", label: "GRT", name: "The Graph" },
  { symbol: "KRAKEN:ICPUSD", label: "ICP", name: "Internet Computer" },
  { symbol: "KRAKEN:INJUSD", label: "INJ", name: "Injective" },
  { symbol: "KRAKEN:SUIUSD", label: "SUI", name: "Sui" },
  { symbol: "KRAKEN:TRXUSD", label: "TRX", name: "Tron" },
  { symbol: "KRAKEN:SHIBUSD", label: "SHIB", name: "Shiba Inu" },
];

const QUICK_COINS = ALL_COINS.slice(0, 6);

interface TradingChartProps {
  className?: string;
  onCoinChange?: (epic: string) => void;
}

function TradingChartInner({ className, onCoinChange }: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const [selectedSymbol, setSelectedSymbol] = useState("KRAKEN:BTCUSD");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const selectedCoinInfo = ALL_COINS.find((c) => c.symbol === selectedSymbol);

  const filteredCoins = useMemo(() => {
    if (!searchQuery) return ALL_COINS;
    const q = searchQuery.toLowerCase();
    return ALL_COINS.filter(
      (c) => c.label.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
    );
  }, [searchQuery]);

  // Detect dark theme
  const isDark = typeof document !== "undefined"
    ? document.documentElement.getAttribute("data-theme") !== "light"
    : true;

  // Embed the TradingView Advanced Chart Widget
  useEffect(() => {
    if (!containerRef.current) return;

    // Clear previous widget
    containerRef.current.innerHTML = "";

    const widgetContainer = document.createElement("div");
    widgetContainer.className = "tradingview-widget-container";
    widgetContainer.style.height = "100%";
    widgetContainer.style.width = "100%";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    widgetDiv.style.height = "100%";
    widgetDiv.style.width = "100%";
    widgetContainer.appendChild(widgetDiv);

    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.textContent = JSON.stringify({
      symbol: selectedSymbol,
      interval: "60",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      theme: isDark ? "dark" : "light",
      style: "1",
      locale: "da_DK",
      allow_symbol_change: true,
      support_host: "https://www.tradingview.com",
      hide_side_toolbar: false,
      details: true,
      hotlist: false,
      calendar: false,
      studies: ["STD;SMA", "STD;RSI"],
      show_popup_button: true,
      popup_width: "1200",
      popup_height: "800",
      width: "100%",
      height: "100%",
    });
    widgetContainer.appendChild(script);

    containerRef.current.appendChild(widgetContainer);
  }, [selectedSymbol, isDark]);

  // Close dropdown
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setSearchOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const handleCoinChange = (symbol: string) => {
    setSelectedSymbol(symbol);
    setSearchOpen(false);
    setSearchQuery("");
    onCoinChange?.(symbol.replace("KRAKEN:", ""));
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card backdrop-blur-sm shadow-sm flex flex-col overflow-hidden",
        className
      )}
    >
      {/* Quick coin selector */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-border">
        <div className="flex gap-1">
          {QUICK_COINS.map((coin) => (
            <button
              key={coin.symbol}
              onClick={() => handleCoinChange(coin.symbol)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                selectedSymbol === coin.symbol
                  ? "bg-accent-muted text-accent"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-card-hover"
              )}
            >
              {coin.label}
            </button>
          ))}
        </div>

        {/* Search dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setSearchOpen(!searchOpen)}
            className={cn(
              "px-2 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1 focus-visible:ring-1 focus-visible:ring-accent focus-visible:outline-none",
              searchOpen
                ? "bg-accent-muted text-accent"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-card-hover"
            )}
          >
            {selectedCoinInfo && !QUICK_COINS.find((c) => c.symbol === selectedSymbol) ? (
              <span className="bg-accent-muted text-accent px-1.5 py-0.5 rounded text-[10px] mr-1 font-semibold">
                {selectedCoinInfo.label}
              </span>
            ) : null}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <span>Flere</span>
          </button>

          {searchOpen && (
            <div className="absolute top-full left-0 mt-1 w-64 max-w-[calc(100vw-2rem)] bg-bg-card border border-border rounded-lg shadow-xl z-50 overflow-hidden">
              <div className="p-2 border-b border-border">
                <input
                  type="text"
                  placeholder="Søg coin..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs bg-bg-primary border border-border rounded-md text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
                  autoFocus
                />
              </div>
              <div className="max-h-64 overflow-y-auto">
                {filteredCoins.length === 0 ? (
                  <div className="px-3 py-4 text-xs text-text-muted text-center">
                    Ingen coins fundet
                  </div>
                ) : (
                  filteredCoins.map((coin) => (
                    <button
                      key={coin.symbol}
                      onClick={() => handleCoinChange(coin.symbol)}
                      className={cn(
                        "w-full px-3 py-2 text-left text-xs flex items-center justify-between hover:bg-bg-card-hover transition-colors",
                        selectedSymbol === coin.symbol && "bg-accent-muted"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-text-primary w-12">{coin.label}</span>
                        <span className="text-text-secondary">{coin.name}</span>
                      </div>
                      {selectedSymbol === coin.symbol && (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="text-accent">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* TradingView Advanced Chart Widget */}
      <div ref={containerRef} className="flex-1 min-h-[550px]" />
    </div>
  );
}

export const TradingChart = memo(TradingChartInner);
