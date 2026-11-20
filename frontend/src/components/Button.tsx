import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger";
const VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-white hover:brightness-110 active:brightness-95",
  secondary: "border border-border bg-surface-2 text-text hover:border-muted active:bg-surface",
  danger: "bg-danger text-white hover:brightness-110 active:brightness-95",
};

export function Button({ variant = "secondary", className = "", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex min-h-8 items-center justify-center gap-2 rounded-input px-3 py-1.5 font-medium transition disabled:opacity-50 ${VARIANT[variant]} ${className}`}
    />
  );
}
