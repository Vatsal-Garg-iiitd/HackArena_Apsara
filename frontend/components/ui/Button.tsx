import { ButtonHTMLAttributes } from "react";
import { clsx } from "clsx";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({ className, variant = "secondary", ...props }: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex h-9 items-center justify-center gap-2 rounded border px-3 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "border-gain/60 bg-gain/15 text-ink-50 hover:bg-gain/20",
        variant === "secondary" && "border-surface-700 bg-surface-850 text-ink-200 hover:bg-surface-800",
        variant === "ghost" && "border-transparent bg-transparent text-ink-400 hover:bg-surface-850 hover:text-ink-50",
        className
      )}
      {...props}
    />
  );
}
