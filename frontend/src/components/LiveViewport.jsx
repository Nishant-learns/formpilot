import React, { useState } from 'react';
import { Eye, Maximize2, Minimize2, Power, RefreshCw, Radio, Shield, ZoomIn } from 'lucide-react';

export default function LiveViewport({ screenshot, agentRunning, currentSection, onStop }) {
  const [isFullscreen, setIsFullscreen] = useState(false);

  return (
    <div className={`bg-slate-900 border border-slate-800 rounded-2xl flex flex-col overflow-hidden shadow-xl ${
      isFullscreen ? 'fixed inset-4 z-50 bg-slate-950/95 backdrop-blur-xl border-amber-500/50' : 'h-[520px]'
    }`}>
      {/* Viewport Top Bar */}
      <div className="bg-slate-950 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
          </div>
          <span className="text-slate-600 font-mono text-xs">|</span>
          <div className="flex items-center gap-2">
            <Radio className={`w-3.5 h-3.5 ${agentRunning ? 'text-emerald-400 animate-pulse' : 'text-slate-500'}`} />
            <span className="text-xs font-semibold text-slate-300 font-mono tracking-wide">
              {agentRunning ? 'LIVE PLAYWRIGHT STREAM (1280x800)' : 'BROWSER VIEWPORT STANDBY'}
            </span>
          </div>
          <span className="text-xs font-bold px-2 py-0.5 rounded bg-slate-800 text-amber-300 border border-slate-700">
            Section {currentSection || 1}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {agentRunning && (
            <button
              onClick={onStop}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/40 text-xs font-bold transition-all"
              title="Immediately abort automated operations and kill browser"
            >
              <Power className="w-3.5 h-3.5" />
              <span>Emergency Stop</span>
            </button>
          )}

          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            title={isFullscreen ? 'Exit Fullscreen' : 'Expand Viewport'}
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Main Stream Canvas */}
      <div className="relative flex-1 bg-slate-950 flex items-center justify-center overflow-auto p-2">
        {screenshot ? (
          <div className="relative max-h-full max-w-full flex items-center justify-center">
            <img
              src={screenshot}
              alt="Live Playwright Viewport"
              className="max-h-full max-w-full object-contain rounded-lg border border-slate-800 shadow-2xl transition-all"
            />
            {agentRunning && (
              <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-lg">
                <div className="w-full h-1 bg-gradient-to-r from-transparent via-amber-400/50 to-transparent animate-scanline opacity-75" />
              </div>
            )}
          </div>
        ) : (
          <div className="text-center p-8 max-w-md">
            <div className="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center mx-auto mb-4 text-slate-600 shadow-inner">
              <Eye className="w-8 h-8" />
            </div>
            <h3 className="text-sm font-bold text-slate-300">
              Live Browser Viewport Inactive
            </h3>
            <p className="text-xs text-slate-500 mt-2 leading-relaxed">
              When you launch an application, real-time high-resolution frames of government portals (RRB, SSC, BPSC, CSBC or Simulator) will stream here with adaptive hydration tracking.
            </p>
          </div>
        )}
      </div>

      {/* Viewport Footer Bar */}
      <div className="bg-slate-950/80 px-4 py-2 border-t border-slate-800/80 text-[11px] text-slate-500 flex items-center justify-between font-mono">
        <div className="flex items-center gap-3">
          <span>Non-Blocking HTTP Commit Enforced</span>
          <span>•</span>
          <span>checkVisibility() + Rect &gt; 0</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-400">
          <Shield className="w-3.5 h-3.5 text-amber-500" />
          <span>Pre-Payment Quarantine Ready</span>
        </div>
      </div>
    </div>
  );
}
