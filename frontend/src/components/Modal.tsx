import { useEffect, useId, useRef, type ReactNode } from "react";

/** Modal berbasis <dialog>: fokus terkunci & Esc menutup secara native (08-ui-ux.md §6). */
export function Modal({ open, onClose, title, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-full max-w-lg rounded-card border border-border bg-surface p-0 text-text"
    >
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <h2 id={titleId} className="text-base font-semibold">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Tutup"
          className="flex h-8 w-8 items-center justify-center rounded-input text-muted hover:bg-surface-2 hover:text-text"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>
      <div className="px-6 py-4">{children}</div>
    </dialog>
  );
}
