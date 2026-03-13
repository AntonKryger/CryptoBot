export const LANGUAGES = ["en", "da", "de", "es"] as const;
export type Language = (typeof LANGUAGES)[number];

export const LANGUAGE_LABELS: Record<Language, string> = {
  en: "English",
  da: "Dansk",
  de: "Deutsch",
  es: "Español",
};

export interface LandingTranslations {
  nav: { pricing: string; login: string; getStarted: string };
  hero: { line1: string; line2: string; line3: string; getStarted: string; discoverHow: string };
  statement: { part1: string; highlight1: string; part2: string; highlight2: string };
  dashboard: {
    balance: string; todayPl: string; openPositions: string; winRate: string;
    ofMax: string; balanceHistory: string; recentTrades: string;
  };
  stats: { totalVolume: string; tradesExecuted: string; uptime: string; avgExecution: string };
  comparison: {
    title1: string; strikethrough: string; title2: string;
    manualTitle: string; botTitle: string;
    manual: string[]; bot: string[];
  };
  features: {
    signal: { label: string; title1: string; title2: string; desc: string; liveOutput: string; confidence: string };
    risk: {
      label: string; title1: string; title2: string; desc: string;
      gates: string[]; gatesLabel: string; gatesSub: string;
    };
    transparency: { label: string; title1: string; title2: string; desc: string; balance: string; today: string };
  };
  pricing: {
    label: string; title: string; recommended: string; then: string; perMonth: string; getStarted: string;
  };
  cta: { line1: string; line2: string; getStarted: string };
  footer: { privacy: string; terms: string; support: string };
}

const en: LandingTranslations = {
  nav: { pricing: "Pricing", login: "Log in", getStarted: "Get Started" },
  hero: { line1: "Trade.", line2: "Sleep.", line3: "Profit.", getStarted: "Get Started", discoverHow: "Discover how" },
  statement: {
    part1: "We built an AI that watches the crypto markets",
    highlight1: "so you don't have to.",
    part2: "It analyzes. It executes. It manages risk.",
    highlight2: "You check your dashboard.",
  },
  dashboard: {
    balance: "Balance", todayPl: "Today P/L", openPositions: "Open Positions", winRate: "Win Rate",
    ofMax: "of 5 max", balanceHistory: "Balance History", recentTrades: "Recent Trades",
  },
  stats: { totalVolume: "Total Volume", tradesExecuted: "Trades Executed", uptime: "Uptime (30d)", avgExecution: "Avg. Execution" },
  comparison: {
    title1: "Manual trading is", strikethrough: "exhausting", title2: "obsolete",
    manualTitle: "Manual Trading", botTitle: "With CryptoBot",
    manual: [
      "Glued to charts 8+ hours/day",
      "Emotional decisions under pressure",
      "Miss signals while sleeping",
      "Inconsistent risk management",
      "Slow order execution",
    ],
    bot: [
      "AI monitors markets 24/7/365",
      "Data-driven decisions, zero emotion",
      "Never misses a signal, any timezone",
      "7 hard gates enforce every trade",
      "Sub-second API execution",
    ],
  },
  features: {
    signal: {
      label: "Signal Engine", title1: "AI that sees what", title2: "you can't",
      desc: "Our signal engine analyzes technical indicators, market sentiment, and on-chain data across 6 pairs simultaneously. It finds high-probability setups — and acts in milliseconds.",
      liveOutput: "LIVE SIGNAL OUTPUT", confidence: "BUY — 87% confidence",
    },
    risk: {
      label: "Risk Management", title1: "Seven gates.", title2: "Zero compromise.",
      desc: "Every single trade — no exceptions — must pass through 7 independent safety checks before execution.",
      gates: [
        "Trading hours verification", "Circuit breaker check", "Max positions limit",
        "Minimum interval between trades", "ADX ≥ 20 (trend strength)", "Risk/Reward ≥ 2:1", "Risk ≤ 1.5% of balance",
      ],
      gatesLabel: "independent safety gates", gatesSub: "on every single trade",
    },
    transparency: {
      label: "Full Transparency", title1: "Every trade.", title2: "Every detail.",
      desc: "Real-time dashboard with balance history, P/L tracking, trade logs, and Telegram alerts. No black boxes — you see exactly what your bot does and why.",
      balance: "Balance", today: "Today",
    },
  },
  pricing: { label: "Pricing", title: "Invest in your edge.", recommended: "Recommended", then: "then", perMonth: "/month", getStarted: "Get Started" },
  cta: { line1: "Stop watching charts.", line2: "Start living.", getStarted: "Get Started" },
  footer: { privacy: "Privacy", terms: "Terms", support: "Support" },
};

const da: LandingTranslations = {
  nav: { pricing: "Priser", login: "Log ind", getStarted: "Kom i gang" },
  hero: { line1: "Trade.", line2: "Sleep.", line3: "Profit.", getStarted: "Kom i gang", discoverHow: "Se hvordan" },
  statement: {
    part1: "Vi har bygget en AI der overvåger kryptomarkederne",
    highlight1: "så du ikke behøver.",
    part2: "Den analyserer. Den eksekverer. Den styrer risikoen.",
    highlight2: "Du tjekker dit dashboard.",
  },
  dashboard: {
    balance: "Saldo", todayPl: "Dagens P/L", openPositions: "Åbne positioner", winRate: "Win Rate",
    ofMax: "af 5 maks", balanceHistory: "Saldohistorik", recentTrades: "Seneste handler",
  },
  stats: { totalVolume: "Samlet volumen", tradesExecuted: "Handler udført", uptime: "Oppetid (30d)", avgExecution: "Gns. eksekvering" },
  comparison: {
    title1: "Manuel trading er", strikethrough: "udmattende", title2: "forældet",
    manualTitle: "Manuel trading", botTitle: "Med CryptoBot",
    manual: [
      "Klistret til charts 8+ timer om dagen",
      "Følelsesladede beslutninger under pres",
      "Misser signaler mens du sover",
      "Inkonsekvent risikostyring",
      "Langsom ordreeksekvering",
    ],
    bot: [
      "AI overvåger markederne 24/7/365",
      "Datadrevne beslutninger, nul følelser",
      "Misser aldrig et signal, uanset tidszone",
      "7 hard gates på hver eneste handel",
      "Sub-sekund API-eksekvering",
    ],
  },
  features: {
    signal: {
      label: "Signal Engine", title1: "AI der ser hvad", title2: "du ikke kan",
      desc: "Vores signal engine analyserer tekniske indikatorer, markedsstemning og on-chain data på tværs af 6 par samtidig. Den finder high-probability setups — og handler på millisekunder.",
      liveOutput: "LIVE SIGNAL OUTPUT", confidence: "KØB — 87% konfidens",
    },
    risk: {
      label: "Risikostyring", title1: "Syv gates.", title2: "Nul kompromis.",
      desc: "Hver eneste handel — ingen undtagelser — skal igennem 7 uafhængige sikkerhedstjek før eksekvering.",
      gates: [
        "Handelstider verificeret", "Circuit breaker tjek", "Maks positioner",
        "Minimum interval mellem handler", "ADX ≥ 20 (trendstyrke)", "Risk/Reward ≥ 2:1", "Risiko ≤ 1,5% af saldo",
      ],
      gatesLabel: "uafhængige sikkerhedsgates", gatesSub: "på hver eneste handel",
    },
    transparency: {
      label: "Fuld gennemsigtighed", title1: "Hver handel.", title2: "Hvert detalje.",
      desc: "Real-time dashboard med saldohistorik, P/L tracking, handelslog og Telegram-alerts. Ingen sorte bokse — du ser præcis hvad din bot gør og hvorfor.",
      balance: "Saldo", today: "I dag",
    },
  },
  pricing: { label: "Priser", title: "Investér i din fordel.", recommended: "Anbefalet", then: "derefter", perMonth: "/md", getStarted: "Kom i gang" },
  cta: { line1: "Stop med at stirre på charts.", line2: "Begynd at leve.", getStarted: "Kom i gang" },
  footer: { privacy: "Privatlivspolitik", terms: "Vilkår", support: "Support" },
};

const de: LandingTranslations = {
  nav: { pricing: "Preise", login: "Anmelden", getStarted: "Loslegen" },
  hero: { line1: "Trade.", line2: "Sleep.", line3: "Profit.", getStarted: "Loslegen", discoverHow: "Erfahre wie" },
  statement: {
    part1: "Wir haben eine KI gebaut, die die Kryptomärkte überwacht",
    highlight1: "damit du es nicht musst.",
    part2: "Sie analysiert. Sie handelt. Sie managt das Risiko.",
    highlight2: "Du checkst dein Dashboard.",
  },
  dashboard: {
    balance: "Saldo", todayPl: "Heute P/L", openPositions: "Offene Positionen", winRate: "Gewinnrate",
    ofMax: "von 5 max", balanceHistory: "Saldoverlauf", recentTrades: "Letzte Trades",
  },
  stats: { totalVolume: "Gesamtvolumen", tradesExecuted: "Trades ausgeführt", uptime: "Uptime (30T)", avgExecution: "Ø Ausführung" },
  comparison: {
    title1: "Manuelles Trading ist", strikethrough: "anstrengend", title2: "veraltet",
    manualTitle: "Manuelles Trading", botTitle: "Mit CryptoBot",
    manual: [
      "8+ Stunden täglich Charts starren",
      "Emotionale Entscheidungen unter Druck",
      "Signale im Schlaf verpassen",
      "Inkonsistentes Risikomanagement",
      "Langsame Orderausführung",
    ],
    bot: [
      "KI überwacht Märkte 24/7/365",
      "Datengetriebene Entscheidungen, null Emotion",
      "Verpasst nie ein Signal, egal welche Zeitzone",
      "7 Hard Gates bei jedem Trade",
      "Sub-Sekunden API-Ausführung",
    ],
  },
  features: {
    signal: {
      label: "Signal Engine", title1: "KI die sieht, was", title2: "du nicht kannst",
      desc: "Unsere Signal Engine analysiert technische Indikatoren, Marktstimmung und On-Chain-Daten über 6 Paare gleichzeitig. Sie findet hochwahrscheinliche Setups — und handelt in Millisekunden.",
      liveOutput: "LIVE SIGNAL OUTPUT", confidence: "KAUF — 87% Konfidenz",
    },
    risk: {
      label: "Risikomanagement", title1: "Sieben Gates.", title2: "Null Kompromisse.",
      desc: "Jeder einzelne Trade — keine Ausnahmen — muss 7 unabhängige Sicherheitschecks passieren.",
      gates: [
        "Handelszeiten-Verifizierung", "Circuit Breaker Check", "Max Positionen",
        "Mindestintervall zwischen Trades", "ADX ≥ 20 (Trendstärke)", "Risk/Reward ≥ 2:1", "Risiko ≤ 1,5% des Saldos",
      ],
      gatesLabel: "unabhängige Sicherheitsgates", gatesSub: "bei jedem einzelnen Trade",
    },
    transparency: {
      label: "Volle Transparenz", title1: "Jeder Trade.", title2: "Jedes Detail.",
      desc: "Echtzeit-Dashboard mit Saldoverlauf, P/L-Tracking, Trade-Logs und Telegram-Alerts. Keine Blackboxes — du siehst genau, was dein Bot tut und warum.",
      balance: "Saldo", today: "Heute",
    },
  },
  pricing: { label: "Preise", title: "Investiere in deinen Vorteil.", recommended: "Empfohlen", then: "dann", perMonth: "/Monat", getStarted: "Loslegen" },
  cta: { line1: "Hör auf, Charts zu starren.", line2: "Fang an zu leben.", getStarted: "Loslegen" },
  footer: { privacy: "Datenschutz", terms: "AGB", support: "Support" },
};

const es: LandingTranslations = {
  nav: { pricing: "Precios", login: "Iniciar sesión", getStarted: "Empezar" },
  hero: { line1: "Trade.", line2: "Sleep.", line3: "Profit.", getStarted: "Empezar", discoverHow: "Descubre cómo" },
  statement: {
    part1: "Construimos una IA que vigila los mercados cripto",
    highlight1: "para que tú no tengas que hacerlo.",
    part2: "Analiza. Ejecuta. Gestiona el riesgo.",
    highlight2: "Tú revisas tu dashboard.",
  },
  dashboard: {
    balance: "Saldo", todayPl: "P/L hoy", openPositions: "Posiciones abiertas", winRate: "Tasa de éxito",
    ofMax: "de 5 máx", balanceHistory: "Historial de saldo", recentTrades: "Operaciones recientes",
  },
  stats: { totalVolume: "Volumen total", tradesExecuted: "Operaciones ejecutadas", uptime: "Uptime (30d)", avgExecution: "Ejec. promedio" },
  comparison: {
    title1: "El trading manual es", strikethrough: "agotador", title2: "obsoleto",
    manualTitle: "Trading manual", botTitle: "Con CryptoBot",
    manual: [
      "Pegado a gráficos 8+ horas al día",
      "Decisiones emocionales bajo presión",
      "Pierdes señales mientras duermes",
      "Gestión de riesgo inconsistente",
      "Ejecución lenta de órdenes",
    ],
    bot: [
      "IA monitorea mercados 24/7/365",
      "Decisiones basadas en datos, cero emoción",
      "Nunca pierde una señal, cualquier zona horaria",
      "7 hard gates en cada operación",
      "Ejecución API en sub-segundos",
    ],
  },
  features: {
    signal: {
      label: "Motor de señales", title1: "IA que ve lo que", title2: "tú no puedes",
      desc: "Nuestro motor de señales analiza indicadores técnicos, sentimiento del mercado y datos on-chain en 6 pares simultáneamente. Encuentra setups de alta probabilidad — y actúa en milisegundos.",
      liveOutput: "SEÑAL EN VIVO", confidence: "COMPRA — 87% confianza",
    },
    risk: {
      label: "Gestión de riesgo", title1: "Siete gates.", title2: "Cero compromisos.",
      desc: "Cada operación — sin excepciones — debe pasar 7 controles de seguridad independientes antes de ejecutarse.",
      gates: [
        "Verificación de horarios", "Circuit breaker check", "Límite de posiciones",
        "Intervalo mínimo entre operaciones", "ADX ≥ 20 (fuerza de tendencia)", "Risk/Reward ≥ 2:1", "Riesgo ≤ 1,5% del saldo",
      ],
      gatesLabel: "gates de seguridad independientes", gatesSub: "en cada operación",
    },
    transparency: {
      label: "Transparencia total", title1: "Cada operación.", title2: "Cada detalle.",
      desc: "Dashboard en tiempo real con historial de saldo, seguimiento P/L, registro de operaciones y alertas Telegram. Sin cajas negras — ves exactamente qué hace tu bot y por qué.",
      balance: "Saldo", today: "Hoy",
    },
  },
  pricing: { label: "Precios", title: "Invierte en tu ventaja.", recommended: "Recomendado", then: "luego", perMonth: "/mes", getStarted: "Empezar" },
  cta: { line1: "Deja de mirar gráficos.", line2: "Empieza a vivir.", getStarted: "Empezar" },
  footer: { privacy: "Privacidad", terms: "Términos", support: "Soporte" },
};

export const translations: Record<Language, LandingTranslations> = { en, da, de, es };
