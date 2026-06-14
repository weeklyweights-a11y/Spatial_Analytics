import type { AlertMessage } from "../types";

interface AlertToastProps {
  alerts: AlertMessage[];
  onDismiss: (id: string) => void;
}

const styles: Record<string, string> = {
  info: "bg-blue-900 border-blue-600",
  warning: "bg-orange-900 border-orange-600",
  critical: "bg-red-900 border-red-600",
};

export function AlertToastStack({ alerts, onDismiss }: AlertToastProps) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
      {alerts.slice(0, 3).map((a) => (
        <button
          key={a.id}
          type="button"
          onClick={() => onDismiss(a.id)}
          className={`w-full text-left p-3 rounded-lg border text-sm text-slate-100 ${styles[a.severity] ?? styles.info}`}
        >
          {a.message}
        </button>
      ))}
    </div>
  );
}
