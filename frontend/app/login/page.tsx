import { Github, Mail } from "lucide-react";
import { Button } from "@/components/ui/Button";

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-surface-950 px-4 text-ink-50">
      <section className="w-full max-w-md border border-surface-700 bg-surface-900 p-6">
        <div className="mb-6">
          <div className="font-mono text-sm font-semibold text-gain">QuantDesk</div>
          <h1 className="mt-3 text-2xl font-semibold">Login</h1>
          <p className="mt-2 text-sm text-ink-500">Authenticate to add stocks and manage your portfolio.</p>
        </div>
        <form className="space-y-4">
          <label className="block">
            <span className="text-sm text-ink-400">Email</span>
            <input className="mt-1 h-10 w-full rounded border border-surface-700 bg-surface-950 px-3 text-sm outline-none focus:border-ink-500" type="email" />
          </label>
          <label className="block">
            <span className="text-sm text-ink-400">Password</span>
            <input className="mt-1 h-10 w-full rounded border border-surface-700 bg-surface-950 px-3 text-sm outline-none focus:border-ink-500" type="password" />
          </label>
          <Button variant="primary" className="w-full" type="button">
            <Mail className="h-4 w-4" />
            Continue
          </Button>
        </form>
        <div className="my-5 h-px bg-surface-700" />
        <div className="grid gap-2">
          <Button className="w-full" type="button">
            <Github className="h-4 w-4" />
            Continue with GitHub
          </Button>
          <Button className="w-full" type="button">
            Continue with Google
          </Button>
        </div>
      </section>
    </main>
  );
}
