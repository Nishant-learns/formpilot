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
} from 'lucide-react';

function sourceLabel(field) {
  if (field.challenge) {
    return {
      text: `${String(field.challenge).toUpperCase()} · human only`,
      className: 'text-sky-300 bg-sky-500/10 border-sky-500/30',
    };
  }
  if (field.value_source === 'vault') return { text: 'Profile value', className: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30' };
  if (field.value_source === 'missing') return { text: 'Needs you', className: 'text-amber-300 bg-amber-500/10 border-amber-500/30' };
  return { text: 'Unknown field', className: 'text-rose-300 bg-rose-500/10 border-rose-500/30' };
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
      text: `Structure changed · v${recipe.version || 1}`,
      className: 'text-amber-300 bg-amber-500/10 border-amber-500/30',
    };
  }
  return {
    icon: <Sparkles className="w-3.5 h-3.5" />,
    text: 'New step · no recipe yet',
    className: 'text-sky-300 bg-sky-500/10 border-sky-500/30',
  };
}

export default function FormMapPanel({ formMap, recipe, runMode, onRescan, rescanning }) {
  const [expanded, setExpanded] = useState(null);
  const [showAll, setShowAll] = useState(false);

  if (!formMap) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center">
        <div className="w-14 h-14 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-center mx-auto mb-3 text-slate-600">
          <Eye className="w-7 h-7" />
        </div>
        <h3 className="text-sm font-bold text-slate-300">Nothing scanned yet</h3>
        <p className="text-xs text-slate-500 mt-2 max-w-sm mx-auto leading-relaxed">
          Start a portal in inspect-only mode to see the normalized form map: fields,
          locator strategies, page type and recipe status. No values or screenshots are stored
          in a recipe.
        </p>
      </div>
    );
  }

  const fields = formMap.fields || [];
  const visibleFields = showAll ? fields : fields.slice(0, 12);
  const badge = recipeBadge(recipe);
  const drift = recipe?.drift;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden flex flex-col max-h-[640px]">
      <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <ScanSearch className="w-4 h-4 text-sky-400 shrink-0" />
          <div className="min-w-0">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wide truncate">
              What the agent sees
            </h3>
            <p className="text-[10px] font-mono text-slate-500 truncate">
              {formMap.display_url || formMap.url || 'unknown page'}
            </p>
          </div>
        </div>
        {runMode === 'inspect' && onRescan && (
          <button
            type="button"
            onClick={onRescan}
            disabled={rescanning}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 border border-sky-500/40 text-[10px] font-bold disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${rescanning ? 'animate-spin' : ''}`} />
            <span>Rescan</span>
          </button>
        )}
      </div>

      <div className="p-4 space-y-3 overflow-y-auto">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-bold px-2 py-1 rounded-lg bg-slate-950 text-slate-200 border border-slate-700 uppercase tracking-wider">
            {formMap.page_type || 'unknown'}
          </span>
          <span className="text-[10px] font-mono text-slate-400">
            {formMap.page_confidence || 0}% confidence
          </span>
          {formMap.step_heading && (
            <span
              className="text-[10px] font-mono text-slate-400 truncate max-w-[240px]"
              title={formMap.step_heading}
            >
              {formMap.step_heading}
            </span>
          )}
          {formMap.active_section_id && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-500">
              #{formMap.active_section_id}
            </span>
          )}
          <span className={`flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-lg border ${badge.className}`}>
            {badge.icon}
            <span>{badge.text}</span>
          </span>
          {formMap.challenge && (
            <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-300 uppercase">
              <Lock className="w-3 h-3" />
              {formMap.challenge} · human only
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {[
            ['Fields', formMap.field_count || 0, 'text-slate-200'],
            ['Known keys', formMap.known_field_count || 0, 'text-emerald-300'],
            ['Needs input', formMap.missing_value_count || 0, 'text-amber-300'],
            ['Human-only', formMap.human_field_count || 0, 'text-sky-300'],
            ['Unknown', formMap.unknown_field_count || 0, 'text-rose-300'],
          ].map(([label, value, className]) => (
            <div key={label} className="rounded-xl bg-slate-950 border border-slate-800 px-3 py-2">
              <div className="text-[9px] uppercase tracking-wider text-slate-500">{label}</div>
              <div className={`text-lg font-extrabold font-mono ${className}`}>{value}</div>
            </div>
          ))}
        </div>

        {drift && (
          <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-[11px] text-amber-200">
            <div className="font-bold flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              Drift detected: {drift.summary}
            </div>
            {(drift.added?.length > 0 || drift.removed?.length > 0 || drift.renamed?.length > 0) && (
              <div className="mt-1.5 space-y-0.5 font-mono text-[10px] text-amber-300/80">
                {drift.added?.map((item) => (
                  <div key={`a-${item.key}`}>+ {item.label || item.key}</div>
                ))}
                {drift.removed?.map((item) => (
                  <div key={`r-${item.key}`}>− {item.label || item.key}</div>
                ))}
                {drift.renamed?.map((item) => (
                  <div key={`n-${item.from}`}>~ {item.old_label || item.from} → {item.new_label || item.to}</div>
                ))}
              </div>
            )}
            <div className="mt-1 text-[10px] text-amber-300/70">
              The live page wins. FormPilot re-observed the real fields and will ask before using
              a stale locator.
            </div>
          </div>
        )}

        {formMap.captcha?.present && (
          <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-[11px] text-amber-200 flex items-start gap-2">
            <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Security check detected ({formMap.captcha.kinds?.join(', ') || 'unknown'}). There is
              no solver: the live browser pauses for a human.
            </span>
          </div>
        )}
        {formMap.live_photo_required && (
          <div className="rounded-xl bg-sky-500/10 border border-sky-500/30 px-3 py-2 text-[11px] text-sky-200 flex items-start gap-2">
            <Tag className="w-4 h-4 shrink-0 mt-0.5" />
            <span>This page asks for a live photo. Capture it with your own camera at the checkpoint.</span>
          </div>
        )}

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Fields and locators
            </span>
            {fields.length > 12 && (
              <button
                type="button"
                onClick={() => setShowAll(!showAll)}
                className="text-[10px] font-semibold text-sky-300 hover:text-sky-200"
              >
                {showAll ? 'Show fewer' : `Show all ${fields.length}`}
              </button>
            )}
          </div>
          <div className="space-y-1.5">
            {visibleFields.map((field) => {
              const source = sourceLabel(field);
              const open = expanded === field.index;
              const locators = field.locators || [];
              return (
                <div key={`${field.index}-${field.key}`} className="rounded-xl bg-slate-950 border border-slate-800 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setExpanded(open ? null : field.index)}
                    className="w-full px-3 py-2 text-left flex items-start justify-between gap-2 hover:bg-slate-900/70"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {open ? <ChevronDown className="w-3.5 h-3.5 text-slate-500 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />}
                        <span className="text-xs font-semibold text-slate-200 truncate">
                          {field.label || field.name || field.key}
                        </span>
                        {field.required && <span className="text-red-400 text-[10px]">*</span>}
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 mt-1 pl-5">
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                          {field.type || 'text'}
                        </span>
                        <span className="text-[9px] font-mono text-sky-300/80">
                          {field.semantic_key || field.suggested_key || field.key}
                        </span>
                        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${source.className}`}>
                          {source.text}
                        </span>
                        {field.confidence > 0 && (
                          <span className="text-[9px] font-mono text-slate-500">{field.confidence}%</span>
                        )}
                      </div>
                    </div>
                    <Fingerprint className="w-3.5 h-3.5 text-slate-600 shrink-0 mt-0.5" />
                  </button>
                  {open && (
                    <div className="px-3 pb-2.5 pt-1 border-t border-slate-800/80 space-y-1.5">
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Locator ladder</div>
                      {locators.map((locator, index) => (
                        <div key={index} className="flex items-center gap-2 text-[10px] font-mono">
                          <span className="w-5 text-slate-600">{index + 1}.</span>
                          <span className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-400 border border-slate-800">
                            {locator.strategy}
                          </span>
                          <span className="text-slate-300 truncate">
                            {locator.value ?? locator.name ?? locator.role ?? ''}
                          </span>
                        </div>
                      ))}
                      {field.suggested_key && !field.semantic_key && (
                        <div className="text-[10px] text-amber-300/80">
                          Suggestion only ({field.confidence}%): FormPilot will ask before using it.
                        </div>
                      )}
                      {field.options?.length > 0 && (
                        <div className="text-[10px] text-slate-400">
                          {field.options.length} option(s): {field.options.slice(0, 6).map((option) => option.text).join(' · ')}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {fields.length === 0 && (
              <p className="text-xs text-slate-500">No form fields on this page.</p>
            )}
          </div>
        </div>

        {formMap.next_actions?.length > 0 && (
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              Next actions
            </div>
            <div className="space-y-1">
              {formMap.next_actions.map((action, index) => (
                <div key={index} className="flex items-center justify-between gap-2 rounded-lg bg-slate-950 border border-slate-800 px-2.5 py-1.5">
                  <span className="text-[11px] text-slate-300 truncate">{action.text}</span>
                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border shrink-0 ${
                    action.blocked
                      ? 'text-red-300 bg-red-500/10 border-red-500/30'
                      : 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30'
                  }`}>
                    {action.blocked ? 'human only' : 'navigation'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-slate-800 pt-2 text-[9px] font-mono text-slate-600">
          <span className="truncate">sha256:{formMap.fingerprint_short || '—'}</span>
          <span>{formMap.portal || ''}</span>
        </div>
      </div>
    </div>
  );
}
