import React from 'react';
import {
  ShieldCheck,
  Bot,
  Volume2,
  VolumeX,
  Cloud,
  Settings,
  FileText,
  Image as ImageIcon,
} from 'lucide-react';

export default function Header({
  agentRunning,
  engineConfig,
  onOpenSettings,
  onOpenVault,
  onOpenBiometrics,
  voiceEnabled,
  setVoiceEnabled,
  currentGate,
}) {
  const cloudActive = engineConfig?.effective_mode === 'cloud' || engineConfig?.mode === 'cloud';
  const paymentReview = currentGate?.gate_type === 'PRE_PAYMENT_SAFETY_LOCK';

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur-md px-5 py-3 sticky top-0 z-40 flex items-center justify-between">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-600 via-orange-500 to-amber-400 flex items-center justify-center text-slate-950 font-black text-xl shadow-lg shadow-orange-500/20 border border-amber-300/30">
            FP
          </div>
          <span className="absolute -bottom-1 -right-1 w-3.5 h-3.5 bg-emerald-500 rounded-full border-2 border-slate-900 animate-pulse" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-extrabold text-base tracking-tight text-white flex items-center gap-1.5">
              Form<span className="text-amber-400">Pilot</span>
            </h1>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/25 px-2 py-0.5 rounded-full">
              Guided applications
            </span>
          </div>
          <p className="text-xs text-slate-400 flex items-center gap-1.5">
            <span>Fill official forms with confidence</span>
            <span className="text-slate-600">•</span>
            <span className="text-emerald-400 font-medium flex items-center gap-0.5">
              <ShieldCheck className="w-3.5 h-3.5" /> You stay in control
            </span>
          </p>
        </div>
      </div>

      {/* Status */}
      <div className="hidden lg:flex items-center gap-3">
        <div
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border ${
            paymentReview
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              : agentRunning
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 animate-pulse'
              : 'bg-slate-800 text-slate-400 border-slate-700'
          }`}
        >
          <Bot className="w-3.5 h-3.5" />
          <span>
            {paymentReview
              ? currentGate?.final_action === 'submission'
                ? 'Review before submitting'
                : 'Review before payment'
              : agentRunning
              ? 'Filling the form with you'
              : 'Ready when you are'}
          </span>
        </div>

        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-500/40 text-cyan-300 transition-colors shadow-sm"
          title="Open connection settings"
        >
          <Cloud className="w-3.5 h-3.5 text-cyan-400" />
          <span>{cloudActive ? 'Cloud browser connected' : 'Using this device'}</span>
        </button>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2.5">
        <button
          onClick={() => setVoiceEnabled(!voiceEnabled)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
            voiceEnabled
              ? 'bg-amber-500/10 text-amber-300 border-amber-500/30 shadow-sm'
              : 'bg-slate-800/60 text-slate-400 border-slate-700 hover:text-slate-200'
          }`}
          title="Turn spoken guidance on or off"
        >
          {voiceEnabled ? (
            <>
              <Volume2 className="w-3.5 h-3.5 text-amber-400" />
              <span>Voice guidance: on</span>
            </>
          ) : (
            <>
              <VolumeX className="w-3.5 h-3.5" />
              <span>Voice guidance: off</span>
            </>
          )}
        </button>

        <button
          onClick={onOpenBiometrics}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
        >
          <ImageIcon className="w-3.5 h-3.5 text-violet-400" />
          <span>Photo &amp; signature</span>
        </button>

        <button
          onClick={onOpenVault}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-amber-500/20 to-orange-500/20 hover:from-amber-500/30 hover:to-orange-500/30 text-amber-300 border border-amber-500/40 transition-all shadow-sm"
        >
          <FileText className="w-3.5 h-3.5 text-amber-400" />
          <span>My details</span>
        </button>

        <button
          onClick={onOpenSettings}
          className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 transition-colors"
          title="Connection settings"
        >
          <Settings className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
