import React from 'react';
import { 
  ShieldCheck, 
  Bot, 
  Volume2, 
  VolumeX, 
  Server, 
  Cloud, 
  Settings, 
  FileText, 
  Image as ImageIcon, 
  AlertTriangle 
} from 'lucide-react';

export default function Header({
  agentRunning,
  engineConfig,
  onOpenSettings,
  onOpenVault,
  onOpenBiometrics,
  voiceEnabled,
  setVoiceEnabled,
  currentGate
}) {
  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur-md px-5 py-3 sticky top-0 z-40 flex items-center justify-between">
      {/* Brand Identity */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-600 via-orange-500 to-amber-400 flex items-center justify-center text-slate-950 font-black text-xl shadow-lg shadow-orange-500/20 border border-amber-300/30">
            CB
          </div>
          <span className="absolute -bottom-1 -right-1 w-3.5 h-3.5 bg-emerald-500 rounded-full border-2 border-slate-900 animate-pulse" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-extrabold text-base tracking-tight text-white flex items-center gap-1.5">
              Form<span className="text-amber-400">Pilot</span>
            </h1>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/25 px-2 py-0.5 rounded-full">
              AI Cyber Bhaiya
            </span>
          </div>
          <p className="text-xs text-slate-400 flex items-center gap-1.5">
            <span>Autonomous Examination & Form Operations Agent</span>
            <span className="text-slate-600">•</span>
            <span className="text-emerald-400 font-medium flex items-center gap-0.5">
              <ShieldCheck className="w-3.5 h-3.5" /> NIC & .gov.in Locked
            </span>
          </p>
        </div>
      </div>

      {/* Center Status Indicators */}
      <div className="hidden lg:flex items-center gap-3">
        {/* Agent State Pill */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border ${
          currentGate?.gate_type === 'PRE_PAYMENT_SAFETY_LOCK'
            ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
            : agentRunning
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 animate-pulse'
            : 'bg-slate-800 text-slate-400 border-slate-700'
        }`}>
          <Bot className="w-3.5 h-3.5" />
          <span>
            {currentGate?.gate_type === 'PRE_PAYMENT_SAFETY_LOCK'
              ? 'Safety Lock Active (Quarantined)'
              : agentRunning
              ? 'Bhaiya is Actively Driving Portal'
              : 'Agent Standby (Ready to Apply)'}
          </span>
        </div>

        {/* Engine Mode Pill */}
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-500/40 text-cyan-300 transition-colors shadow-sm"
          title="Click to configure TinyFish Cloud Browser & Tetra Proxy"
        >
          <Cloud className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
          <span>TinyFish Cloud (Tetra {engineConfig.proxy_region?.toUpperCase() || 'IN'} • Stealth)</span>
        </button>

        {/* Real Phone Push Notification Pill */}
        <a
          href="https://ntfy.sh/bharatpilot_otp"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-950/40 hover:bg-emerald-900/50 border border-emerald-500/40 text-emerald-300 transition-colors"
          title="Open live phone push notification channel on phone or desktop"
        >
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          <span>Live OTP: ntfy.sh/bharatpilot_otp</span>
        </a>
      </div>

      {/* Action Controls & Utilities */}
      <div className="flex items-center gap-2.5">
        {/* Voice Toggle */}
        <button
          onClick={() => setVoiceEnabled(!voiceEnabled)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
            voiceEnabled
              ? 'bg-amber-500/10 text-amber-300 border-amber-500/30 shadow-sm'
              : 'bg-slate-800/60 text-slate-400 border-slate-700 hover:text-slate-200'
          }`}
          title="Toggle Bhaiya's Audio Commentary in Hindi"
        >
          {voiceEnabled ? (
            <>
              <Volume2 className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
              <span>Bhaiya Ki Aawaz: ON</span>
            </>
          ) : (
            <>
              <VolumeX className="w-3.5 h-3.5" />
              <span>Aawaz: Muted</span>
            </>
          )}
        </button>

        {/* Biometrics Studio Button */}
        <button
          onClick={onOpenBiometrics}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
        >
          <ImageIcon className="w-3.5 h-3.5 text-violet-400" />
          <span>Biometric Studio</span>
        </button>

        {/* Candidate One-Vault Button */}
        <button
          onClick={onOpenVault}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-amber-500/20 to-orange-500/20 hover:from-amber-500/30 hover:to-orange-500/30 text-amber-300 border border-amber-500/40 transition-all shadow-sm"
        >
          <FileText className="w-3.5 h-3.5 text-amber-400" />
          <span>One-Vault Profile</span>
        </button>

        {/* Engine Settings Button */}
        <button
          onClick={onOpenSettings}
          className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 transition-colors"
          title="TinyFish API & Engine Settings"
        >
          <Settings className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
