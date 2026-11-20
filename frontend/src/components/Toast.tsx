import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Tone = "info" | "success" | "error";
interface ToastItem {
  id: number;
  text: string;
  tone: Tone;
}

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => {});
const TONE_CLASS: Record<Tone, string> = {
  info: "border-border",
  success: "border-success",
  error: "border-danger",
};
const TONE_LABEL: Record<Tone, string> = { info: "Info", success: "Berhasil", error: "Gagal" };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const show = useCallback((text: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div role="status" aria-live="polite" className="fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className={`rounded-card border-l-4 bg-surface-2 px-4 py-3 ${TONE_CLASS[t.tone]}`}>
            <span className="sr-only">{TONE_LABEL[t.tone]}: </span>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
