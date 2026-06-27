"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, BarChart3, CheckCircle2, LineChart, LockKeyhole, LogOut, ShieldCheck, Sparkles } from "lucide-react";
import type { User } from "@supabase/supabase-js";
import { Button } from "@/components/ui/Button";
import { supabase } from "@/lib/supabase";

const stats = [
  ["NIFTY 50", "+0.74%", "25,112.40"],
  ["SENSEX", "+0.61%", "82,445.21"],
  ["BANK NIFTY", "-0.18%", "56,903.10"]
];

const features = [
  ["Live market lens", "Track index movement, OHLCV candles, and market breadth from one clean terminal.", LineChart],
  ["Portfolio-ready profile", "Create a secure trader profile with Supabase authentication before entering the workspace.", ShieldCheck],
  ["Focused decision flow", "Switch between benchmarks, drill into companies, and compare momentum without visual clutter.", BarChart3]
];

export function LandingPage() {
  const [user, setUser] = useState<User | null>(null);
  const [loadingUser, setLoadingUser] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setLoadingUser(false);
      return;
    }

    supabase.auth.getUser().then(({ data }) => {
      setUser(data.user ?? null);
      setLoadingUser(false);
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
      setLoadingUser(false);
    });

    return () => data.subscription.unsubscribe();
  }, []);

  async function handleLogout() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setUser(null);
  }

  return (
    <main className="min-h-screen bg-white text-slate-800">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 md:px-8">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded bg-slate-900 text-white">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="text-lg font-semibold tracking-tight">QuantDesk</span>
          </Link>

          <nav className="hidden items-center gap-6 text-sm font-medium text-slate-500 md:flex">
            <a href="#markets" className="hover:text-slate-900">Markets</a>
            <a href="#features" className="hover:text-slate-900">Platform</a>
            <a href="#security" className="hover:text-slate-900">Security</a>
          </nav>

          <div className="flex items-center gap-2">
            {user ? (
              <>
                <Link
                  href="/dashboard"
                  className="inline-flex h-9 items-center justify-center rounded border border-slate-900 bg-slate-900 px-3 text-sm font-semibold text-white transition-colors hover:bg-slate-800"
                >
                  Dashboard
                </Link>
                <button
                  type="button"
                  onClick={handleLogout}
                  aria-label="Logout"
                  title="Logout"
                  className="grid h-9 w-9 place-items-center rounded border border-slate-200 text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-900"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  className="inline-flex h-9 items-center justify-center rounded border border-slate-200 px-3 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900"
                >
                  Login
                </Link>
                <Link
                  href="/signup"
                  className="inline-flex h-9 items-center justify-center rounded border border-slate-900 bg-slate-900 px-3 text-sm font-semibold text-white transition-colors hover:bg-slate-800"
                >
                  Sign up
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-10 px-4 py-12 md:px-8 lg:grid-cols-[minmax(0,1fr)_520px] lg:py-16">
        <div className="flex min-h-[520px] flex-col justify-center">
          <div className="mb-5 inline-flex w-fit items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            Secure trading workspace
          </div>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-slate-950 md:text-6xl">
            QuantDesk
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-600">
            A sharp market terminal for Indian equity analysis, index monitoring, and portfolio-ready research workflows.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href={user ? "/dashboard" : "/signup"}
              className="inline-flex h-11 items-center gap-2 rounded border border-slate-900 bg-slate-900 px-5 text-sm font-semibold text-white transition-colors hover:bg-slate-800"
            >
              {user ? "Open dashboard" : "Create free account"}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href={user ? "/dashboard" : "/login"}
              className="inline-flex h-11 items-center rounded border border-slate-200 px-5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50"
            >
              {user ? "View markets" : "Login"}
            </Link>
          </div>
          {!loadingUser && !user && (
            <p className="mt-4 text-sm text-slate-500">Login or sign up from the header to enter the dashboard.</p>
          )}
        </div>

        <div id="markets" className="flex items-center">
          <section className="w-full rounded-lg border border-slate-200 bg-slate-950 p-4 text-white shadow-xl">
            <div className="mb-4 flex items-center justify-between border-b border-white/10 pb-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300">Market pulse</p>
                <h2 className="mt-1 text-xl font-semibold">Indian Indices</h2>
              </div>
              <LockKeyhole className="h-5 w-5 text-slate-400" />
            </div>
            <div className="space-y-3">
              {stats.map(([name, change, value]) => {
                const positive = change.startsWith("+");
                return (
                  <div key={name} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded border border-white/10 bg-white/[0.03] px-4 py-3">
                    <span className="text-sm font-semibold">{name}</span>
                    <span className={`font-mono text-sm font-semibold ${positive ? "text-emerald-300" : "text-red-300"}`}>{change}</span>
                    <span className="font-mono text-sm text-slate-300">{value}</span>
                  </div>
                );
              })}
            </div>
            <div className="mt-5 h-44 rounded border border-white/10 bg-[linear-gradient(180deg,rgba(16,185,129,0.12),rgba(15,23,42,0))] p-4">
              <svg viewBox="0 0 520 160" className="h-full w-full" role="img" aria-label="Market trend preview">
                <path d="M10 124 C70 94 106 108 152 76 S242 58 292 72 374 30 430 48 490 46 510 24" fill="none" stroke="#34d399" strokeWidth="5" strokeLinecap="round" />
                <path d="M10 124 C70 94 106 108 152 76 S242 58 292 72 374 30 430 48 490 46 510 24 L510 160 L10 160 Z" fill="rgba(52,211,153,0.12)" />
              </svg>
            </div>
          </section>
        </div>
      </section>

      <section id="features" className="border-y border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-7xl gap-4 px-4 py-10 md:grid-cols-3 md:px-8">
          {features.map(([title, body, Icon]) => (
            <article key={title as string} className="rounded-lg border border-slate-200 bg-white p-5">
              <Icon className="h-5 w-5 text-emerald-600" />
              <h2 className="mt-4 text-base font-semibold text-slate-900">{title as string}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">{body as string}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="security" className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-10 md:flex-row md:items-center md:justify-between md:px-8">
        <div>
          <h2 className="text-2xl font-semibold text-slate-950">Authentication powered by Supabase</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            Email/password signup, login, logout, protected dashboard access, and OAuth callback handling are wired into the app flow.
          </p>
        </div>
        <Button type="button" variant="primary" onClick={() => window.location.assign(user ? "/dashboard" : "/signup")}>
          {user ? "Open dashboard" : "Start trading profile"}
          <ArrowRight className="h-4 w-4" />
        </Button>
      </section>
    </main>
  );
}
