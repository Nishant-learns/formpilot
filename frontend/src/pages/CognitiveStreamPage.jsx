import React, { useState } from 'react';
import { Terminal, Brain, Eye, CheckCircle2, Zap, ChevronRight, Download, Filter } from 'lucide-react';
import CognitiveStream from '../components/CognitiveStream';

export default function CognitiveStreamPage({ events, voiceEnabled }) {
  const handleExportLogs = () => {
    const blob = new Blob([JSON.stringify(events, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `formpilot-cognitive-stream-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      {/* Header Bar */}
      <div className="px-6 py-5 border-b border-white/[0.08] bg-slate-950/40 backdrop-blur-md shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1">
              <span>Workstation</span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-sky-400 font-semibold">Cognitive Stream</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-white tracking-tight">Agent Cognitive Thought Stream</h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-sky-500/10 text-sky-300 border border-sky-500/30">
                <Terminal className="w-3 h-3" />
                Live Reasoning Ledger
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportLogs}
              disabled={events.length === 0}
              className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors disabled:opacity-40"
            >
              <Download className="w-3.5 h-3.5 text-slate-400" />
              <span>Export Stream JSON</span>
            </button>
          </div>
        </div>

        {/* Stream Stats Ribbon */}
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Total Stream Events</span>
            <span className="text-white font-bold font-mono text-base">{events.length}</span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Sensing Observations</span>
            <span className="text-cyan-400 font-mono font-bold">
              {events.filter((e) => e.phase === 'SENSE').length} Sensed
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Decisions & Rules</span>
            <span className="text-amber-300 font-mono font-bold">
              {events.filter((e) => e.phase === 'DECIDE').length} Resolved
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Dispatched Actions</span>
            <span className="text-emerald-400 font-mono font-bold">
              {events.filter((e) => e.phase === 'ACT').length} Dispatched
            </span>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-6xl w-full mx-auto flex-1 flex flex-col min-h-0">
        <div className="glass-panel rounded-3xl border border-white/[0.08] flex-1 flex flex-col min-h-[500px] overflow-hidden p-4">
          <CognitiveStream events={events} voiceEnabled={voiceEnabled} />
        </div>
      </div>
    </div>
  );
}
