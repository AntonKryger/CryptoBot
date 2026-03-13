// Exchange Provider Registry — single source of truth for all supported exchanges

export type ExchangeId = "capital_com" | "binance" | "kraken" | "bybit" | "okx" | "coinbase";
export type ExchangeStatus = "active" | "coming_soon";

export interface CredentialField {
  key: string;
  label: string;
  type: "text" | "password";
  placeholder: string;
}

export interface ExchangeProvider {
  id: ExchangeId;
  name: string;
  status: ExchangeStatus;
  logo: string;
  hasEnvironments: boolean;
  credentialFields: CredentialField[];
}

export const EXCHANGE_PROVIDERS: Record<ExchangeId, ExchangeProvider> = {
  capital_com: {
    id: "capital_com",
    name: "Capital.com",
    status: "active",
    logo: "/exchanges/capital-com.svg",
    hasEnvironments: true,
    credentialFields: [
      { key: "apiKey", label: "API Key", type: "text", placeholder: "Enter your Capital.com API key" },
      { key: "apiPassword", label: "API Password", type: "password", placeholder: "Enter your API password" },
      { key: "identifier", label: "Identifier / Email", type: "text", placeholder: "Your Capital.com email" },
    ],
  },
  binance: {
    id: "binance",
    name: "Binance",
    status: "coming_soon",
    logo: "/exchanges/binance.svg",
    hasEnvironments: false,
    credentialFields: [
      { key: "apiKey", label: "API Key", type: "text", placeholder: "Enter your Binance API key" },
      { key: "apiSecret", label: "API Secret", type: "password", placeholder: "Enter your API secret" },
    ],
  },
  kraken: {
    id: "kraken",
    name: "Kraken",
    status: "coming_soon",
    logo: "/exchanges/kraken.svg",
    hasEnvironments: false,
    credentialFields: [
      { key: "apiKey", label: "API Key", type: "text", placeholder: "Enter your Kraken API key" },
      { key: "apiSecret", label: "API Secret", type: "password", placeholder: "Enter your API secret" },
    ],
  },
  bybit: {
    id: "bybit",
    name: "Bybit",
    status: "coming_soon",
    logo: "/exchanges/bybit.svg",
    hasEnvironments: false,
    credentialFields: [
      { key: "apiKey", label: "API Key", type: "text", placeholder: "Enter your Bybit API key" },
      { key: "apiSecret", label: "API Secret", type: "password", placeholder: "Enter your API secret" },
    ],
  },
  okx: {
    id: "okx",
    name: "OKX",
    status: "coming_soon",
    logo: "/exchanges/okx.svg",
    hasEnvironments: false,
    credentialFields: [
      { key: "apiKey", label: "API Key", type: "text", placeholder: "Enter your OKX API key" },
      { key: "apiSecret", label: "API Secret", type: "password", placeholder: "Enter your API secret" },
    ],
  },
  coinbase: {
    id: "coinbase",
    name: "Coinbase",
    status: "coming_soon",
    logo: "/exchanges/coinbase.svg",
    hasEnvironments: false,
    credentialFields: [
      { key: "apiKey", label: "API Key", type: "text", placeholder: "Enter your Coinbase API key" },
      { key: "apiSecret", label: "API Secret", type: "password", placeholder: "Enter your API secret" },
    ],
  },
};

export function getExchangeProvider(id: ExchangeId): ExchangeProvider {
  return EXCHANGE_PROVIDERS[id];
}

export const ALL_EXCHANGES = Object.values(EXCHANGE_PROVIDERS);
export const ACTIVE_EXCHANGES = ALL_EXCHANGES.filter((e) => e.status === "active");
export const COMING_SOON_EXCHANGES = ALL_EXCHANGES.filter((e) => e.status === "coming_soon");
