import { clsx } from "clsx";

export function Badge({
  children,
  tone = "neutral"
}: {
  children: React.ReactNode;
  tone?: "neutral" | "positive" | "negative" | "warning";
}) {
  return (
    <span
      className={clsx(
        "inline-flex h-6 items-center rounded border px-2 text-xs font-medium",
        tone === "neutral" && "border-surface-700 bg-surface-850 text-ink-200",
        tone === "positive" && "border-gain/40 bg-gain/10 text-gain",
        tone === "negative" && "border-loss/40 bg-loss/10 text-loss",
        tone === "warning" && "border-warn/40 bg-warn/10 text-warn"
      )}
    >
      {children}
    </span>
  );
}
