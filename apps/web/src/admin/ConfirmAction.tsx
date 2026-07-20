import { useState } from "react";

type ConfirmActionProps = {
  label: string;
  message: string;
  confirmLabel?: string;
  className?: string;
  disabled?: boolean;
  onConfirm: () => void;
};

export function ConfirmAction({
  label,
  message,
  confirmLabel = "Confirm delete",
  className,
  disabled,
  onConfirm,
}: ConfirmActionProps) {
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <button
        className={className}
        type="button"
        disabled={disabled}
        onClick={() => setConfirming(true)}
      >
        {label}
      </button>
    );
  }

  return (
    <span className="confirm-action" role="group" aria-label={`${label} confirmation`}>
      <span>{message}</span>
      <button
        className="reject"
        type="button"
        disabled={disabled}
        onClick={() => {
          setConfirming(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </button>
      <button type="button" disabled={disabled} onClick={() => setConfirming(false)}>
        Cancel
      </button>
    </span>
  );
}