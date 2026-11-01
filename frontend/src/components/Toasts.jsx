import React, { useEffect } from 'react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

const TONES = {
  success: {
    icon: CheckCircle2,
    wrap: 'border-emerald-500/40 bg-emerald-950/80 text-emerald-100 glow-emerald',
    iconClass: 'text-emerald-400',
  },
  error: {
    icon: AlertTriangle,
    wrap: 'border-rose-500/40 bg-rose-950/80 text-rose-100',
    iconClass: 'text-rose-400',
  },
  info: {
    icon: Info,
    wrap: 'border-indigo-500/40 bg-indigo-950/80 text-indigo-100 glow-indigo',
    iconClass: 'text-indigo-400',
  },
};

function Toast({ toast, onDismiss }) {
  const tone = TONES[toast.tone] || TONES.info;
  const Icon = tone.icon;

  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), toast.tone === 'error' ? 7000 : 4500);
    return () => clearTimeout(timer);
  }, [toast.id, toast.tone, onDismiss]);

  return (
    <div
      role="status"
      className={`toast-in glass-panel-elevated specular-top flex w-full max-w-sm items-start gap-2.5 rounded-2xl border px-4 py-3 shadow-2xl backdrop-blur-xl ${tone.wrap}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone.iconClass}`} />
      <p className="flex-1 text-xs font-medium leading-relaxed">{toast.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="rounded-lg p-1 text-slate-400 transition-colors hover:text-white hover:bg-white/[0.08]"
        aria-label="Dismiss notification"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export default function Toasts({ toasts, onDismiss }) {
  if (!toasts.length) return null;
  return (
    <div className="pointer-events-none fixed bottom-24 right-4 z-[70] flex w-[calc(100%-2rem)] max-w-sm flex-col items-end gap-2">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto w-full">
          <Toast toast={toast} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  );
}
