import type { Metadata } from "next";
import localFont from "next/font/local";
import { Inter } from "next/font/google";
import { Suspense } from "react";
import { ThemeForcer } from "@/components/ThemeForcer";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrainsMono = localFont({
  src: [
    {
      path: "./fonts/JetBrainsMono-Regular.woff2",
      weight: "400",
      style: "normal",
    },
    {
      path: "./fonts/JetBrainsMono-Bold.woff2",
      weight: "700",
      style: "normal",
    },
  ],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: {
    default: "CryptoBot — AI-Powered Crypto Trading Platform",
    template: "%s — CryptoBot",
  },
  description:
    "Autonomous AI crypto trading on your Capital.com account. Fully managed, transparent, profitable. Start trading smarter today.",
  keywords: [
    "crypto trading",
    "AI trading bot",
    "Capital.com",
    "automated trading",
    "cryptocurrency",
    "bitcoin",
    "ethereum",
  ],
  authors: [{ name: "CryptoBot" }],
  creator: "CryptoBot",
  metadataBase: new URL("https://cryptobot.dk"),
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://cryptobot.dk",
    siteName: "CryptoBot",
    title: "CryptoBot — AI-Powered Crypto Trading Platform",
    description:
      "Autonomous AI crypto trading on your Capital.com account. Fully managed, transparent, profitable.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "CryptoBot — AI-Powered Crypto Trading",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "CryptoBot — AI-Powered Crypto Trading Platform",
    description:
      "Autonomous AI crypto trading on your Capital.com account. Fully managed, transparent, profitable.",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="midnight" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}
      >
        <Suspense>
          <ThemeForcer />
        </Suspense>
        {children}
      </body>
    </html>
  );
}
