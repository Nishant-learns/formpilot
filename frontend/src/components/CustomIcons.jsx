import React from 'react';

/**
 * Bespoke SVG Icon Library for FormPilot
 * Designed with a consistent 24x24 viewBox, 1.5px stroke, and subtle neon gradients.
 */

// Official Institutional Emblems & Badges
export function GovEmblemIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <circle cx="12" cy="12" r="10" strokeWidth="1.5" className="stroke-emerald-500/40" />
      <circle cx="12" cy="12" r="7" strokeWidth="1.2" strokeDasharray="2 2" className="stroke-emerald-400" />
      <path d="M12 7v10M7 12h10" strokeWidth="1.5" strokeLinecap="round" className="stroke-emerald-300" />
      <circle cx="12" cy="12" r="2" fill="currentColor" className="text-emerald-400" />
    </svg>
  );
}

export function UPSCSealIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <path d="M12 2L4 6v6c0 5.5 3.5 10.5 8 12 4.5-1.5 8-6.5 8-12V6l-8-4z" strokeWidth="1.5" className="stroke-indigo-400" fill="rgba(99, 102, 241, 0.1)" />
      <path d="M9 11l2 2 4-4" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="stroke-emerald-400" />
      <circle cx="12" cy="7.5" r="1" fill="currentColor" className="text-indigo-300" />
    </svg>
  );
}

export function SSCSealIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <rect x="3" y="4" width="18" height="16" rx="3" strokeWidth="1.5" className="stroke-sky-400" fill="rgba(56, 189, 248, 0.08)" />
      <path d="M7 8h10M7 12h7M7 16h4" strokeWidth="1.6" strokeLinecap="round" className="stroke-sky-300" />
      <circle cx="17" cy="15" r="2" strokeWidth="1.5" className="stroke-emerald-400" />
    </svg>
  );
}

export function RailwaySealIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <rect x="4" y="3" width="16" height="14" rx="3" strokeWidth="1.5" className="stroke-amber-400" fill="rgba(245, 158, 11, 0.08)" />
      <path d="M4 11h16M8 7h.01M16 7h.01M4 17l-2 4M20 17l2 4M8 17v4M16 17v4" strokeWidth="1.5" strokeLinecap="round" className="stroke-amber-400" />
      <circle cx="12" cy="14" r="1.5" fill="currentColor" className="text-amber-300" />
    </svg>
  );
}

// Security, Verification & Autonomous AI Icons
export function SecurityShieldIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" strokeWidth="1.5" className="stroke-emerald-400" fill="rgba(16, 185, 129, 0.1)" />
      <path d="M9 12l2 2 4-4" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="stroke-emerald-300" />
    </svg>
  );
}

export function NeuralSparkleIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4L12 2z" strokeWidth="1.5" className="stroke-indigo-400" fill="rgba(99, 102, 241, 0.15)" />
      <circle cx="19" cy="5" r="1.5" fill="currentColor" className="text-violet-400" />
      <circle cx="5" cy="19" r="1" fill="currentColor" className="text-sky-400" />
    </svg>
  );
}

export function BiometricFingerprintIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <path d="M12 11c-1.5 0-2.5 1-2.5 2.5v3.5M12 7c-3.5 0-6 2.5-6 6v3.5M12 3c-5.5 0-9.5 4-9.5 9.5v3.5M15.5 13.5v3.5M18 13c0-3.5-2.5-6-6-6M21.5 12.5c0-5.5-4-9.5-9.5-9.5" strokeWidth="1.6" strokeLinecap="round" className="stroke-violet-400" />
    </svg>
  );
}

export function BiometricFaceScanIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" strokeWidth="1.5" strokeLinecap="round" className="stroke-indigo-400" />
      <circle cx="9" cy="10" r="1.2" fill="currentColor" className="text-indigo-300" />
      <circle cx="15" cy="10" r="1.2" fill="currentColor" className="text-indigo-300" />
      <path d="M10 15c1 1 3 1 4 0M12 11v2" strokeWidth="1.4" strokeLinecap="round" className="stroke-indigo-300" />
    </svg>
  );
}

export function AudioWaveformIcon({ active = false, className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 11v2M21 12h1" strokeWidth="2" strokeLinecap="round" className={active ? "stroke-indigo-400 animate-pulse" : "stroke-slate-500"} />
    </svg>
  );
}

export function CrosshairScannerIcon({ className = "w-5 h-5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <circle cx="12" cy="12" r="8" strokeWidth="1.2" strokeDasharray="3 3" className="stroke-indigo-400/60" />
      <circle cx="12" cy="12" r="3" strokeWidth="1.5" className="stroke-indigo-300" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" strokeWidth="1.5" strokeLinecap="round" className="stroke-indigo-400" />
    </svg>
  );
}

export function CommandKeyIcon({ className = "w-3.5 h-3.5", ...props }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className={className} {...props}>
      <path d="M18 9V6a3 3 0 0 0-3-3H9a3 3 0 0 0-3 3v3h12zm0 6v3a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3v-3h12zm-9 0H6a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3h3v12zm6 0h3a3 3 0 0 0 3-3V9a3 3 0 0 0-3-3h-3v12z" strokeWidth="1.6" className="stroke-slate-400" />
    </svg>
  );
}
