import { useId, type ReactNode } from "react";

/** Field berlabel dengan pesan bantuan & error yang terhubung via aria-describedby. */
export function Field({ label, hint, error, children }: {
  label: string;
  hint?: string;
  error?: string;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block font-medium">{label}</label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && <p id={hintId} className="text-xs text-muted">{hint}</p>}
      {error && <p id={errorId} className="text-xs text-danger">{error}</p>}
    </div>
  );
}

export const inputClass =
  "min-h-8 w-full rounded-input border border-border bg-surface-2 px-2 py-1 aria-[invalid=true]:border-danger";
