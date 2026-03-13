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

// Generate realistic mock candle data
function generateMockCandles(epic: string, timeframe: string): CandlestickData<Time>[] {
  const now = Math.floor(Date.now() / 1000);
  const intervals: Record<string, number> = {
    MINUTE_15: 15 * 60,
    HOUR: 60 * 60,
    HOUR_4: 4 * 60 * 60,
    DAY: 24 * 60 * 60,
  };
  const interval = intervals[timeframe] || 3600;
  const count = 200;

  // Base prices per coin
  const bases: Record<string, number> = {
    BTCUSD: 84000,
    ETHUSD: 2120,
    SOLUSD: 128,
    AVAXUSD: 22,
    LINKUSD: 14.5,
    LTCUSD: 93,
  };
  const base = bases[epic] || 100;
  const volatility = base * 0.008; // 0.8% volatility per candle

  const candles: CandlestickData<Time>[] = [];
  let price = base * (0.95 + Math.random() * 0.1); // Start -5% to +5%

  for (let i = 0; i < count; i++) {
    const time = (now - (count - i) * interval) as Time;
    const change = (Math.random() - 0.48) * volatility; // slight upward bias
    const open = price;
    const close = open + change;
    const high = Math.max(open, close) + Math.random() * volatility * 0.5;
    const low = Math.min(open, close) - Math.random() * volatility * 0.5;

    candles.push({
      time,
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low: parseFloat(low.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
    });
    price = close;
  }

  return candles;
}

interface TradingChartProps {
  className?: string;
  onPriceUpdate?: (price: number, change: number) => void;
}

export function TradingChart({ className, onPriceUpdate }: TradingChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const [selectedCoin, setSelectedCoin] = useState("BTCUSD");
  const [selectedTimeframe, setSelectedTimeframe] = useState("HOUR");
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [priceChange, setPriceChange] = useState(0);

  const updateChart = useCallback(
    (epic: string, timeframe: string) => {
      if (!seriesRef.current || !volumeSeriesRef.current) return;

      const candles = generateMockCandles(epic, timeframe);
      seriesRef.current.setData(candles);

      // Generate volume data
      const volumeData = candles.map((c) => ({
        time: c.time,
        value: Math.floor(Math.random() * 1000 + 200),
        color:
          c.close >= c.open
            ? "rgba(34, 197, 94, 0.3)"
            : "rgba(239, 68, 68, 0.3)",
      }));
      volumeSeriesRef.current.setData(volumeData);

      // Update price info
      const last = candles[candles.length - 1];
      const first = candles[0];
      if (last && first) {
        const change = ((last.close - first.open) / first.open) * 100;
        setCurrentPrice(last.close);
        setPriceChange(change);
        onPriceUpdate?.(last.close, change);
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

  // Update data when coin/timeframe changes
  useEffect(() => {
    updateChart(selectedCoin, selectedTimeframe);
  }, [selectedCoin, selectedTimeframe, updateChart]);

  const coinLabel = COINS.find((c) => c.epic === selectedCoin)?.label || selectedCoin;

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
                onClick={() => setSelectedCoin(coin.epic)}
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
                  ? currentPrice.toLocaleString("en-US", { minimumFractionDigits: 2 })
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

      {/* Chart */}
      <div ref={chartContainerRef} className="flex-1 min-h-[400px]" />
    </div>
  );
}
