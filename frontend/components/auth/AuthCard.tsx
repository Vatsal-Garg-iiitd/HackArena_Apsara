"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { ArrowLeft, Mail } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { upsertProfile } from "@/lib/profile";
import { isSupabaseConfigured, supabase } from "@/lib/supabase";

type AuthMode = "login" | "signup";

export function AuthCard({ mode }: { mode: AuthMode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const isLogin = mode === "login";
  const nextPath = useMemo(() => {
    const next = searchParams.get("next");
    return next?.startsWith("/") ? next : "/dashboard";
  }, [searchParams]);

  async function handleEmailAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);

    if (!supabase) {
      setMessage("Supabase is not configured. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY to .env.local.");
      return;
    }

    setLoading(true);
    try {
      if (isLogin) {
        const { data, error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) {
          setMessage("No matching account was found. Please sign up first if you are a new user.");
          return;
        }
        if (data.user) {
          await upsertProfile(data.user);
        }
        router.push(nextPath);
        return;
      }

      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: fullName
          },
          emailRedirectTo: `${window.location.origin}/auth/callback`
        }
      });

      if (error) {
        const existingUser =
          error.message.toLowerCase().includes("already") ||
          error.message.toLowerCase().includes("registered") ||
          error.message.toLowerCase().includes("exists");
        setMessage(existingUser ? "This email already has an account. Please login instead." : error.message);
        return;
      }

      if (data.user) {
        await upsertProfile(data.user);
      }

      if (data.session) {
        router.push(nextPath);
        return;
      }

      setMessage("Signup successful. Check your email to confirm your account, then login.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle() {
    setMessage(null);

    if (!supabase) {
      setMessage("Supabase is not configured. Add your Supabase project URL and anon key first.");
      return;
    }

    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(nextPath)}`
      }
    });
  }

  return (
    <main className="grid min-h-screen place-items-center bg-slate-50 px-4 py-10 text-slate-800">
      <section className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <Link href="/" className="mb-5 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900">
          <ArrowLeft className="h-4 w-4" />
          Back to home
        </Link>
        <div className="mb-6">
          <div className="font-mono text-sm font-semibold text-[#079b83]">QuantDesk</div>
          <h1 className="mt-3 text-2xl font-semibold">{isLogin ? "Login" : "Create account"}</h1>
          <p className="mt-2 text-sm text-slate-500">
            {isLogin
              ? "Login to manage your market profile and portfolio workspace."
              : "New here? Sign up first to create your trading profile."}
          </p>
        </div>

        {!isSupabaseConfigured && (
          <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Supabase env variables are missing. Configure `.env.local` before using auth.
          </div>
        )}

        <form className="space-y-4" onSubmit={handleEmailAuth}>
          {!isLogin && (
            <label className="block">
              <span className="text-sm font-medium text-slate-600">Full name</span>
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#079b83]"
                type="text"
                required
              />
            </label>
          )}
          <label className="block">
            <span className="text-sm font-medium text-slate-600">Email</span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#079b83]"
              type="email"
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-600">Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-[#079b83]"
              type="password"
              minLength={6}
              required
            />
          </label>
          <Button variant="primary" className="w-full" type="submit" disabled={loading}>
            <Mail className="h-4 w-4" />
            {loading ? "Please wait..." : isLogin ? "Login" : "Sign up"}
          </Button>
        </form>

        <div className="my-5 h-px bg-slate-200" />

        <Button className="w-full" type="button" onClick={handleGoogle}>
          <span className="font-semibold">G</span>
          Continue with Google
        </Button>

        {message && <p className="mt-4 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">{message}</p>}

        <p className="mt-5 text-center text-sm text-slate-500">
          {isLogin ? "New user?" : "Already have an account?"}{" "}
          <Link href={isLogin ? "/signup" : "/login"} className="font-semibold text-[#079b83]">
            {isLogin ? "Sign up first" : "Login"}
          </Link>
        </p>
      </section>
    </main>
  );
}
