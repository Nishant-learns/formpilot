import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  Fingerprint,
  Lock,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Tag,
  Search,
  Copy,
  Check,
} from 'lucide-react';

function sourceLabel(field) {
  if (field.challenge) {
    return {
      text: `${String(field.challenge).toUpperCase()} · human only`,
      className: 'text-sky-300 bg-sky-500/10 border-sky-500/30',
    };
  }
  if (field.value_source === 'vault') {
    return { text: 'Vault profile', className: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30' };
  }
  if (field.value_source === 'missing') {
    return { text: 'Missing fact', className: 'text-amber-300 bg-amber-500/10 border-amber-500/30' };
  }
  return { text: 'Unregistered field', className: 'text-rose-300 bg-rose-500/10 border-rose-500/30' };
}

function recipeBadge(recipe) {
  const status = recipe?.status || 'new';
  if (status === 'match') {
    return {
      icon: <CheckCircle2 className="w-3.5 h-3.5" />,
      text: `Recipe v${recipe.version || 1} matched`,
      className: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30',
    };
  }
  if (status === 'drift') {
    return {
      icon: <AlertTriangle className="w-3.5 h-3.5" />,
      text: `Structural drift · v${recipe.version || 1}`,
      className: 'text-amber-300 bg-amber-500/10 border-amber-500/30',
    };
  }
  return {
    icon: <Sparkles className="w-3.5 h-3.5" />,
    text: 'Zero recipe · runtime probe',
    className: 'text-sky-300 bg-sky-500/10 border-sky-500/30',
  };
}

function strategyTone(strategy) {
  const s = String(strategy || '').toLowerCase();
  if (s.includes('id')) return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  if (s.includes('name')) return 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30';
  if (s.includes('xpath')) return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
  if (s.includes('role') || s.includes('aria')) return 'bg-violet-500/15 text-violet-300 border-violet-500/30';
  return 'bg-sky-500/15 text-sky-300 border-sky-500/30';
}

export default function FormMapPanel({ formMap, recipe, runMode, onRescan, rescanning }) {
  const [expanded, setExpanded] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [copiedLocator, setCopiedLocator] = useState(null);

  if (!formMap) {
    return (
      <div className="glass-panel-elevated specular-top rounded-3xl p-8 text-center h-full min-h-[460px] flex flex-col items-center justify-center shadow-2xl border border-white/[0.08]">
        <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mx-auto mb-4 text-indigo-400 shadow-inner">
          <Eye className="w-8 h-8" />
        </div>
        <h3 className="text-sm font-extrabold text-white">No Semantic Field Map</h3>
        <p className="text-xs text-slate-400 mt-2 max-w-sm mx-auto leading-relaxed">
          Launch a recruitment portal or run in inspect-only mode to watch the agent analyze the DOM structure, calculate locator fallback ladders, and verify schema drift.
        </p>
      </div>
    );
  }

  const fields = formMap.fields || [];
  const knownCount = fields.filter((field) => !field.challenge && field.value_source === 'vault').length;
  const missingCount = fields.filter((field) => !field.challenge && field.value_source === 'missing').length;
  const humanCount = fields.filter((field) => Boolean(field.challenge)).length;
  const unknownCount = Math.max(0, fields.length - knownCount - missingCount - humanCount);

  const filterDefs = [
    { id: 'all', label: 'All', count: fields.length, tone: 'text-slate-300' },
    { id: 'profile', label: 'Profile', count: knownCount, tone: 'text-emerald-300' },
    { id: 'missing', label: 'Missing', count: missingCount, tone: 'text-amber-300' },
    { id: 'human', label: 'Human-only', count: humanCount, tone: 'text-sky-300' },
    { id: 'unknown', label: 'Unmapped', count: unknownCount, tone: 'text-rose-300' },
  ];

  const filteredFields = fields.filter((field) => {
    if (statusFilter === 'profile' && (field.challenge || field.value_source !== 'vault')) return false;
    if (statusFilter === 'missing' && (field.challenge || field.value_source !== 'missing')) return false;
    if (statusFilter === 'human' && !field.challenge) return false;
    if (statusFilter === 'unknown' && (field.challenge || field.value_source === 'vault' || field.value_source === 'missing')) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchLabel = String(field.label || '').toLowerCase().includes(q);
      const matchName = String(field.name || '').toLowerCase().includes(q);
      const matchKey = String(field.key || '').toLowerCase().includes(q);
      const matchSemantic = String(field.semantic_key || '').toLowerCase().includes(q);
      const matchLocators = (field.locators || []).some((loc) =>
        String(loc.value || loc.name || '').toLowerCase().includes(q)
      );
      return matchLabel || matchName || matchKey || matchSemantic || matchLocators;
    }
    return true;
  });

  const visibleFields = showAll ? filteredFields : filteredFields.slice(0, 14);
  const coverage = fields.length ? Math.round((knownCount / fields.length) * 100) : 0;
  const badge = recipeBadge(recipe);
  const drift = recipe?.drift;

  const handleCopyLocator = (val, key) => {
    if (!val) return;
    navigator.clipboard?.writeText(val);
    setCopiedLocator(key);
    setTimeout(() => setCopiedLocator(null), 1800);
  };

  return (
    <div className="glass-panel-elevated specular-top rounded-3xl overflow-hidden flex flex-col h-full min-h-[460px] shadow-2xl border border-white/[0.08]">
      {/* Header */}
      <div className="bg-white/[0.02] px-4 py-3 border-b border-white/[0.08] flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-sky-500/15 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0">
            <ScanSearch className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider truncate">
              DOM Cognitive Telemetry
            </h3>
            <p className="text-[10px] font-mono text-slate-400 truncate">
              {formMap.display_url || formMap.url || 'Live Session Viewport'}
            </p>
          </div>
        </div>
        {runMode === 'inspect' && onRescan && (
          <button
            type="button"
            onClick={onRescan}
            disabled={rescanning}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 border border-sky-500/40 text-[10px] font-bold disabled:opacity-50 transition-all"
          >
            <RefreshCw className={`w-3 h-3 ${rescanning ? 'animate-spin' : ''}`} />
            <span>Rescan</span>
          </button>
        )}
      </div>

      <div className="p-4 space-y-3 overflow-y-auto flex-1 min-h-0">
        {/* Page Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-bold px-2.5 py-1 rounded-xl bg-white/[0.04] text-white border border-white/[0.1] uppercase tracking-wider font-mono">
            {formMap.page_type || 'STANDARD_FORM'}
          </span>
          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-md border border-emerald-500/20 font-bold">
            {formMap.page_confidence || 98}% confidence
          </span>
          {formMap.step_heading && (
            <span
              className="text-[10px] font-mono text-slate-300 truncate max-w-[220px]"
              title={formMap.step_heading}
            >
              {formMap.step_heading}
            </span>
          )}
          <span className={`flex items-center gap-1.5 text-[10px] font-mono px-2.5 py-1 rounded-xl border ${badge.className}`}>
            {badge.icon}
            <span>{badge.text}</span>
          </span>
          {formMap.challenge && (
            <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-300 uppercase">
              <Lock className="w-3 h-3" />
              {formMap.challenge}
            </span>
          )}
        </div>

        {/* Telemetry Metric Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {[
            ['Fields', formMap.field_count || fields.length, 'text-slate-100'],
            ['Profile Keys', knownCount, 'text-emerald-300'],
            ['Needs Input', missingCount, 'text-amber-300'],
            ['Human Barrier', humanCount, 'text-sky-300'],
            ['Unmapped', unknownCount, 'text-rose-300'],
          ].map(([label, value, className]) => (
            <div key={label} className="rounded-2xl bg-slate-950/70 border border-white/[0.08] px-3 py-2">
              <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">{label}</div>
              <div className={`text-lg font-black font-mono mt-0.5 ${className}`}>{value}</div>
            </div>
          ))}
        </div>

        {/* Profile Coverage Bar */}
        {fields.length > 0 && (
          <div className="rounded-2xl border border-white/[0.08] bg-slate-950/70 px-3.5 py-2.5">
            <div className="flex items-center justify-between gap-2 text-[10px]">
              <span className="font-semibold uppercase tracking-wider text-slate-400">Vault Auto-fill Coverage</span>
              <span className="font-mono font-bold text-slate-200">
                {knownCount} of {fields.length} fields · {coverage}%
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-900 border border-white/[0.05]">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  coverage >= 80 ? 'bg-gradient-to-r from-emerald-500 to-teal-400' : coverage >= 40 ? 'bg-gradient-to-r from-amber-500 to-orange-400' : 'bg-rose-500'
                }`}
                style={{ width: `${coverage}%` }}
              />
            </div>
          </div>
        )}

        {/* Drift Alert */}
        {drift && (
          <div className="rounded-2xl bg-amber-500/10 border border-amber-500/30 px-3.5 py-2.5 text-[11px] text-amber-200">
            <div className="font-bold flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>DOM Structural Drift Detected: {drift.summary}</span>
            </div>
            <div className="mt-1 text-[10px] text-amber-300/80">
              Live browser DOM took precedence. FormPilot dynamically recalibrated selectors.
            </div>
          </div>
        )}

        {/* Search & Filter Toolbar */}
        <div className="space-y-2 pt-1">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Filter fields by name, key, or locator..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-950/80 border border-white/[0.08] text-xs text-white placeholder-slate-500 outline-none focus:border-indigo-400 transition-all font-sans"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-2 text-slate-500 hover:text-slate-300 text-xs"
                >
                  ×
                </button>
              )}
            </div>
            {filteredFields.length > 14 && (
              <button
                type="button"
                onClick={() => setShowAll(!showAll)}
                className="text-[10px] font-semibold text-indigo-300 hover:text-indigo-200 shrink-0 px-2.5 py-1.5 rounded-xl bg-white/[0.04] border border-white/[0.08]"
              >
                {showAll ? 'Show fewer' : `Show all (${filteredFields.length})`}
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-1">
            {filterDefs.map((filter) => (
              <button
                key={filter.id}
                type="button"
                onClick={() => {
                  setStatusFilter(filter.id);
                  setShowAll(false);
                  setExpanded(null);
                }}
                className={`flex items-center gap-1.5 rounded-xl border px-2.5 py-1 text-[10px] font-semibold transition-all ${
                  statusFilter === filter.id
                    ? 'border-indigo-500/50 bg-indigo-500/15 text-indigo-200'
                    : 'border-white/[0.06] bg-slate-950/40 text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                }`}
              >
                <span>{filter.label}</span>
                <span className={`font-mono font-bold ${filter.tone}`}>{filter.count}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Field List Accordion */}
        <div className="space-y-2">
          {visibleFields.map((field) => {
            const source = sourceLabel(field);
            const open = expanded === field.index;
            const locators = field.locators || [];

            return (
              <div
                key={`${field.index}-${field.key}`}
                className="rounded-2xl bg-slate-950/70 border border-white/[0.08] overflow-hidden hover:border-white/[0.14] transition-all"
              >
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : field.index)}
                  className="w-full px-3.5 py-2.5 text-left flex items-start justify-between gap-2 hover:bg-white/[0.02]"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0">
                      {open ? (
                        <ChevronDown className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                      )}
                      <span className="text-xs font-bold text-white truncate">
                        {field.label || field.name || field.key}
                      </span>
                      {field.required && <span className="text-red-400 text-[10px] font-bold">*</span>}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1 pl-5">
                      <span className="text-[9px] font-mono px-2 py-0.5 rounded-md bg-white/[0.04] text-slate-400 border border-white/[0.06]">
                        {field.type || 'text'}
                      </span>
                      <span className="text-[9px] font-mono text-indigo-300 font-semibold">
                        {field.semantic_key || field.suggested_key || field.key}
                      </span>
                      <span className={`text-[9px] font-mono px-2 py-0.5 rounded-md border ${source.className}`}>
                        {source.text}
                      </span>
                      {field.confidence > 0 && (
                        <span className="text-[9px] font-mono text-emerald-400/80 font-bold">
                          {field.confidence}%
                        </span>
                      )}
                    </div>
                  </div>
                  <Fingerprint className="w-4 h-4 text-slate-600 shrink-0 mt-1" />
                </button>

                {open && (
                  <div className="px-3.5 pb-3 pt-1 border-t border-white/[0.06] space-y-2 bg-white/[0.01]">
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">
                      Locator Ladder (Multi-Strategy Resolution):
                    </div>
                    {locators.map((locator, idx) => {
                      const locVal = locator.value ?? locator.name ?? locator.role ?? '';
                      const copyId = `${field.index}-${idx}`;
                      return (
                        <div
                          key={idx}
                          className="flex items-center justify-between gap-2 p-1.5 rounded-xl bg-slate-900/80 border border-white/[0.06] text-[10px] font-mono"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="w-4 text-slate-500 shrink-0 font-bold">{idx + 1}.</span>
                            <span className={`px-2 py-0.5 rounded-md border font-semibold shrink-0 ${strategyTone(locator.strategy)}`}>
                              {locator.strategy}
                            </span>
                            <span className="text-slate-200 truncate" title={locVal}>
                              {locVal}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleCopyLocator(locVal, copyId)}
                            className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-white/[0.08] shrink-0"
                            title="Copy locator"
                          >
                            {copiedLocator === copyId ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          {visibleFields.length === 0 && (
            <p className="text-xs text-slate-500 text-center py-6">
              {searchQuery ? 'No fields matching your filter.' : 'No form fields found on this page.'}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
