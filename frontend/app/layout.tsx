import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ProfileBootstrap } from "@/components/auth/ProfileBootstrap";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap"
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap"
});

export const metadata: Metadata = {
  title: "QuantDesk",
  description: "Minimal quantitative trading terminal for market analysis and portfolio tracking."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${jetBrainsMono.variable} font-sans antialiased`} suppressHydrationWarning>
        <ProfileBootstrap />
        {children}
      </body>
    </html>
  );
}
