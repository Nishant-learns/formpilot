import React from 'react';
import { Layers, RefreshCw, ChevronRight, Download, ScanSearch } from 'lucide-react';
import FormMapPanel from '../components/FormMapPanel';

export default function DomTelemetryPage({ formMap, recipe, runMode, onRescan, rescanning }) {
  const handleExportMap = () => {
    if (!formMap) return;
    const blob = new Blob([JSON.stringify(formMap, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `formpilot-dom-map-${new Date().toISOString().slice(0, 10)}.json`;
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
              <span className="text-emerald-400 font-semibold">DOM Telemetry</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-white tracking-tight">DOM Map & Locator Telemetry</h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                <Layers className="w-3 h-3" />
                Live Structural Scanner
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {formMap && (
              <button
                type="button"
                onClick={handleExportMap}
                className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors"
              >
                <Download className="w-3.5 h-3.5 text-slate-400" />
                <span>Export Map JSON</span>
              </button>
            )}
            {onRescan && (
              <button
                type="button"
                onClick={onRescan}
                disabled={rescanning}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-400/40 text-xs font-bold flex items-center gap-2 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${rescanning ? 'animate-spin' : ''}`} />
                <span>{rescanning ? 'Scanning DOM...' : 'Rescan Active Portal'}</span>
              </button>
            )}
          </div>
        </div>

        {/* DOM Metrics Ribbon */}
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Scanned Fields</span>
            <span className="text-white font-bold font-mono text-base">{formMap?.field_count || 0} fields</span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Ready to Commit</span>
            <span className="text-emerald-400 font-mono font-bold">
              {formMap?.fields?.filter((f) => f.value_source === 'vault').length || 0} Ready
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Missing Candidate Facts</span>
            <span className="text-amber-300 font-mono font-bold">
              {formMap?.fields?.filter((f) => f.value_source === 'missing').length || 0} Required
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Recipe Status</span>
            <span className="text-indigo-300 font-mono font-bold">
              {recipe?.status === 'match' ? `Recipe v${recipe.version || 1}` : 'Dynamic Runtime Probe'}
            </span>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-6xl w-full mx-auto flex-1 flex flex-col min-h-0">
        <div className="glass-panel rounded-3xl border border-white/[0.08] flex-1 flex flex-col min-h-[500px] overflow-hidden p-5">
          <FormMapPanel
            formMap={formMap}
            recipe={recipe}
            runMode={runMode}
            onRescan={onRescan}
            rescanning={rescanning}
          />
        </div>
      </div>
    </div>
  );
}
