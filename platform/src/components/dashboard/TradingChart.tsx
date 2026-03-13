"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import { cn } from "@/lib/utils";

const COINS = [
  { epic: "BTCUSD", label: "BTC" },
  { epic: "ETHUSD", label: "ETH" },
  { epic: "SOLUSD", label: "SOL" },
  { epic: "AVAXUSD", label: "AVAX" },
  { epic: "LINKUSD", label: "LINK" },
  { epic: "LTCUSD", label: "LTC" },
];

const TIMEFRAMES = [
  { value: "MINUTE_15", label: "15m" },
  { value: "HOUR", label: "1H" },
  { value: "HOUR_4", label: "4H" },
  { value: "DAY", label: "1D" },
];

interface ChartColors {
  background: string;
  text: string;
  grid: string;
  upColor: string;
  downColor: string;
  borderUp: string;
  borderDown: string;
  wickUp: string;
  wickDown: string;
}

function getThemeColors(): ChartColors {
  const style = getComputedStyle(document.documentElement);
  const isDark = document.documentElement.getAttribute("data-theme") !== "light";

  return {
    background: style.getPropertyValue("--bg-card").trim() || (isDark ? "#1a1f2e" : "#ffffff"),
    text: style.getPropertyValue("--text-secondary").trim() || (isDark ? "#94a3b8" : "#64748b"),
    grid: style.getPropertyValue("--border").trim() || (isDark ? "#2a3150" : "#e2e8f0"),
    upColor: style.getPropertyValue("--success").trim() || "#22c55e",
    downColor: style.getPropertyValue("--danger").trim() || "#ef4444",
    borderUp: style.getPropertyValue("--success").trim() || "#22c55e",
    borderDown: style.getPropertyValue("--danger").trim() || "#ef4444",
    wickUp: style.getPropertyValue("--success").trim() || "#22c55e",
    wickDown: style.getPropertyValue("--danger").trim() || "#ef4444",
  };
}

interface ApiCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

async function fetchCandles(epic: string, resolution: string): Promise<ApiCandle[]> {
  const resp = await fetch(`/api/prices?epic=${epic}&resolution=${resolution}&max=200`);
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  const data = await resp.json();
  return data.candles || [];
}

interface TradingChartProps {
  className?: string;
  onPriceUpdate?: (price: number, change: number) => void;
  onCoinChange?: (epic: string) => void;
}

export function TradingChart({ className, onPriceUpdate, onCoinChange }: TradingChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const [selectedCoin, setSelectedCoin] = useState("BTCUSD");
  const [selectedTimeframe, setSelectedTimeframe] = useState("HOUR");
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [priceChange, setPriceChange] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(
    async (epic: string, timeframe: string) => {
      if (!seriesRef.current || !volumeSeriesRef.current) return;

      setLoading(true);
      setError(null);

      try {
        const apiCandles = await fetchCandles(epic, timeframe);

        if (!apiCandles.length) {
          setError("Ingen data modtaget fra Capital.com");
          return;
        }

        // Convert to lightweight-charts format
        const candles: CandlestickData<Time>[] = apiCandles.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }));

        seriesRef.current.setData(candles);

        // Volume data
        const volumeData = apiCandles.map((c) => ({
          time: c.time as Time,
          value: c.volume,
          color:
            c.close >= c.open
              ? "rgba(34, 197, 94, 0.3)"
              : "rgba(239, 68, 68, 0.3)",
        }));
        volumeSeriesRef.current.setData(volumeData);

        // Update price info
        const last = apiCandles[apiCandles.length - 1];
        const first = apiCandles[0];
        if (last && first) {
          const change = ((last.close - first.open) / first.open) * 100;
          setCurrentPrice(last.close);
          setPriceChange(change);
          onPriceUpdate?.(last.close, change);
        }
      } catch (err) {
        console.error("Chart data error:", err);
        setError(err instanceof Error ? err.message : "Kunne ikke hente data");
      } finally {
        setLoading(false);
      }
    },
    [onPriceUpdate]
  );

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const colors = getThemeColors();

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: colors.background },
        textColor: colors.text,
        fontFamily: "'Inter', -apple-system, sans-serif",
      },
      grid: {
        vertLines: { color: colors.grid, style: 1 },
        horzLines: { color: colors.grid, style: 1 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { labelBackgroundColor: colors.upColor },
        horzLine: { labelBackgroundColor: colors.upColor },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: colors.upColor,
      downColor: colors.downColor,
      borderUpColor: colors.borderUp,
      borderDownColor: colors.borderDown,
      wickUpColor: colors.wickUp,
      wickDownColor: colors.wickDown,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        chart.applyOptions({ width, height });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    // Theme observer
    const themeObserver = new MutationObserver(() => {
      const newColors = getThemeColors();
      chart.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: newColors.background },
          textColor: newColors.text,
        },
        grid: {
          vertLines: { color: newColors.grid },
          horzLines: { color: newColors.grid },
        },
      });
      candleSeries.applyOptions({
        upColor: newColors.upColor,
        downColor: newColors.downColor,
        borderUpColor: newColors.borderUp,
        borderDownColor: newColors.borderDown,
        wickUpColor: newColors.wickUp,
        wickDownColor: newColors.wickDown,
      });
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => {
      resizeObserver.disconnect();
      themeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  // Load data when coin/timeframe changes
  useEffect(() => {
    loadData(selectedCoin, selectedTimeframe);
  }, [selectedCoin, selectedTimeframe, loadData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      loadData(selectedCoin, selectedTimeframe);
    }, 30000);
    return () => clearInterval(interval);
  }, [selectedCoin, selectedTimeframe, loadData]);

  const handleCoinChange = (epic: string) => {
    setSelectedCoin(epic);
    onCoinChange?.(epic);
  };

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-bg-card backdrop-blur-sm shadow-sm flex flex-col",
        className
      )}
    >
      {/* Header: coin selector + price + timeframe */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-border">
        {/* Coin selector */}
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {COINS.map((coin) => (
              <button
                key={coin.epic}
                onClick={() => handleCoinChange(coin.epic)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                  selectedCoin === coin.epic
                    ? "bg-accent text-white"
                    : "text-text-secondary hover:text-text-primary hover:bg-bg-card-hover"
                )}
              >
                {coin.label}
              </button>
            ))}
          </div>

          {/* Price display */}
          {currentPrice !== null && (
            <div className="flex items-center gap-2 ml-3 pl-3 border-l border-border">
              <span className="text-lg font-mono font-semibold text-text-primary">
                {currentPrice >= 1000
                  ? currentPrice.toLocaleString("da-DK", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  : currentPrice.toFixed(4)}
              </span>
              <span
                className={cn(
                  "text-sm font-mono font-medium",
                  priceChange >= 0 ? "text-success" : "text-danger"
                )}
              >
                {priceChange >= 0 ? "+" : ""}
                {priceChange.toFixed(2)}%
              </span>
            </div>
          )}

          {/* Loading indicator */}
          {loading && (
            <div className="ml-2">
              <div className="h-3 w-3 rounded-full border-2 border-accent border-t-transparent animate-spin" />
            </div>
          )}
        </div>

        {/* Timeframe selector */}
        <div className="flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setSelectedTimeframe(tf.value)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                selectedTimeframe === tf.value
                  ? "bg-accent-muted text-accent"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-card-hover"
              )}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 bg-danger/10 text-danger text-xs">
          {error}
        </div>
      )}

      {/* Chart */}
      <div ref={chartContainerRef} className="flex-1 min-h-[400px]" />

      {/* Footer: data source */}
      <div className="px-4 py-1.5 border-t border-border text-[10px] text-text-muted flex justify-between">
        <span>Data: Capital.com (demo) — 30s auto-refresh</span>
        <span>Powered by TradingView Lightweight Charts</span>
      </div>
    </div>
  );
}
