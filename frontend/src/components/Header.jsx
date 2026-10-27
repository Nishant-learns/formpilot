import React from 'react';
import {
  Bot,
  Cloud,
  FileText,
  Image as ImageIcon,
  Pause,
  Play,
  Settings,
  ShieldCheck,
  Volume2,
  VolumeX,
} from 'lucide-react';

function ReadinessRing({ percent }) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  const radius = 9;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  return (
    <span className="relative flex h-7 w-7 items-center justify-center">
      <svg viewBox="0 0 24 24" className="h-7 w-7 -rotate-90">
        <circle cx="12" cy="12" r={radius} fill="none" stroke="currentColor" strokeWidth="2.4" className="text-slate-700" />
        <circle
          cx="12"
          cy="12"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={value >= 80 ? 'text-emerald-400' : value >= 50 ? 'text-amber-400' : 'text-rose-400'}
        />
      </svg>
      <span className="absolute text-[8px] font-extrabold text-slate-200">{value}</span>
    </span>
  );
}

export default function Header({
  agentRunning,
  paused,
  runState,
  engineConfig,
  readiness,
  onOpenSettings,
  onOpenVault,
  onOpenBiometrics,
  onPauseToggle,
  voiceEnabled,
  setVoiceEnabled,
  currentGate,
}) {
  const cloudActive = engineConfig?.effective_mode === 'cloud' || engineConfig?.mode === 'cloud';
  const paymentReview = currentGate?.gate_type === 'PRE_PAYMENT_SAFETY_LOCK';
  const inspectReady = runState === 'INSPECT_READY';
  const finished = ['STOPPED', 'FAILED', 'COMPLETED'].includes(runState);
  const active = agentRunning && !paused;

  return (
    <header className="sticky top-0 z-40 border-b border-slate-800/90 bg-slate-950/85 px-3 py-2.5 backdrop-blur-xl sm:px-5">
      <div className="mx-auto flex w-full max-w-[1560px] items-center justify-between gap-3">
        {/* Brand */}
        <div className="flex min-w-0 items-center gap-3">
          <div className="relative shrink-0">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-amber-300/30 bg-gradient-to-tr from-amber-600 via-orange-500 to-amber-400 text-xl font-black text-slate-950 shadow-lg shadow-orange-500/20">
              FP
            </div>
            <span className={`absolute -bottom-1 -right-1 h-3.5 w-3.5 rounded-full border-2 border-slate-950 ${active ? 'animate-pulse bg-emerald-500' : paused ? 'bg-amber-400' : 'bg-slate-600'}`} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-extrabold tracking-tight text-white">
                Form<span className="text-amber-400">Pilot</span>
              </h1>
              <span className="hidden rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-400 sm:inline">
                Guided applications
              </span>
            </div>
            <p className="hidden items-center gap-1.5 text-[11px] text-slate-400 sm:flex">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              <span>You stay in control</span>
              <span className="text-slate-700">•</span>
              <span className={cloudActive ? 'text-sky-300' : 'text-slate-500'}>
                <Cloud className="mr-0.5 inline h-3 w-3" />
                {cloudActive ? 'Cloud browser' : 'On this device'}
              </span>
            </p>
          </div>
        </div>

        {/* Live state */}
        <div
          className={`hidden items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold md:flex ${
            paymentReview
              ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
              : paused
                ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                : inspectReady
                  ? 'border-sky-500/30 bg-sky-500/10 text-sky-300'
                  : active
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                    : 'border-slate-700 bg-slate-900 text-slate-400'
          }`}
        >
          <Bot className="h-3.5 w-3.5" />
          <span>
            {paymentReview
              ? currentGate?.final_action === 'submission'
                ? 'Review before submitting'
                : 'Review before payment'
              : paused
                ? 'Paused — take your time'
                : inspectReady
                  ? 'Inspect-only · nothing touched'
                  : finished
                    ? 'Session finished'
                    : active
                      ? 'Filling the form with you'
                      : 'Ready when you are'}
          </span>
          {(active || inspectReady) && (
            <span className={`h-1.5 w-1.5 animate-pulse rounded-full ${inspectReady ? 'bg-sky-400' : 'bg-emerald-400'}`} />
          )}
        </div>

        {/* Controls */}
        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          {agentRunning && !currentGate && onPauseToggle && (
            <button
              type="button"
              onClick={onPauseToggle}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-colors ${
                paused
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
                  : 'border-slate-700 bg-slate-800/70 text-slate-200 hover:bg-slate-700'
              }`}
              title={paused ? 'Resume the agent' : 'Pause the agent'}
            >
              {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
              <span className="hidden xl:inline">{paused ? 'Resume' : 'Pause'}</span>
            </button>
          )}

          <button
            type="button"
            onClick={onOpenVault}
            className="flex items-center gap-2 rounded-xl border border-amber-500/35 bg-gradient-to-r from-amber-500/15 to-orange-500/10 px-2 py-1.5 text-[11px] font-bold text-amber-200 transition-colors hover:from-amber-500/25 hover:to-orange-500/20"
            title={readiness ? `Profile ${readiness.percent}% ready — ${readiness.filled} of ${readiness.total} core details saved` : 'Open your saved details'}
          >
            {readiness ? <ReadinessRing percent={readiness.percent} /> : <FileText className="h-4 w-4 text-amber-300" />}
            <span className="hidden sm:inline">My details</span>
            {readiness && <span className="hidden font-mono text-[10px] text-amber-300/80 lg:inline">{readiness.percent}%</span>}
          </button>

          <button
            type="button"
            onClick={() => setVoiceEnabled(!voiceEnabled)}
            className={`hidden items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-colors sm:flex ${
              voiceEnabled
                ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                : 'border-slate-700 bg-slate-800/60 text-slate-400 hover:text-slate-200'
            }`}
            title="Spoken guidance"
          >
            {voiceEnabled ? <Volume2 className="h-3.5 w-3.5" /> : <VolumeX className="h-3.5 w-3.5" />}
            <span className="hidden xl:inline">{voiceEnabled ? 'Voice on' : 'Voice off'}</span>
          </button>

          <button
            type="button"
            onClick={onOpenBiometrics}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-[11px] font-semibold text-slate-200 transition-colors hover:bg-slate-700"
            title="Photo and signature studio"
          >
            <ImageIcon className="h-3.5 w-3.5 text-violet-400" />
            <span className="hidden xl:inline">Photo &amp; signature</span>
          </button>

          <button
            type="button"
            onClick={onOpenSettings}
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
            title="Connection settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
