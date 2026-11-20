import { Modal } from "./Modal";
import { Button } from "./Button";

export function ConfirmDialog({ open, title, message, confirmLabel, danger, busy, onConfirm, onCancel }: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      <p className="text-muted">{message}</p>
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onCancel}>Kembali</Button>
        <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} disabled={busy}>
          {busy ? "Memproses…" : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
