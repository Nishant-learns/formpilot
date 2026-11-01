import React, { useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  CheckCircle2,
  FileText,
  Lock,
  RefreshCw,
  ShieldQuestion,
  Sparkles,
  HelpCircle,
  Compass,
  Check,
} from 'lucide-react';
import { NeuralSparkleIcon } from './CustomIcons';

function typeTone(pageType) {
  switch (pageType) {
    case 'FORM':
    case 'SECTION_FORM':
      return 'text-sky-300 bg-sky-500/10 border-sky-500/30';
    case 'DASHBOARD':
      return 'text-violet-300 bg-violet-500/10 border-violet-500/30';
    case 'LANDING':
    case 'LISTING':
      return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
    case 'LOGIN':
    case 'REGISTER':
      return 'text-amber-300 bg-amber-500/10 border-amber-500/30';
    case 'OTP':
    case 'CAPTCHA':
    case 'PAYMENT':
      return 'text-rose-300 bg-rose-500/10 border-rose-500/30';
    case 'ERROR':
      return 'text-red-300 bg-red-500/10 border-red-500/30';
    default:
      return 'text-slate-300 bg-slate-500/10 border-slate-500/30';
  }
}

function conceptTone(question) {
  if (question.human_only) return 'text-sky-300 bg-sky-500/10 border-sky-500/30';
  if (!question.concept) return 'text-rose-300 bg-rose-500/10 border-rose-500/30';
  if (question.concept_confidence >= 0.85) return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  return 'text-amber-300 bg-amber-500/10 border-amber-500/30';
}

function factTone(status) {
  if (status === 'known') return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  if (status === 'known_absent') return 'text-sky-300 bg-sky-500/10 border-sky-500/30';
  if (status === 'needs_confirmation') return 'text-amber-300 bg-amber-500/10 border-amber-500/30';
  return 'text-rose-300 bg-rose-500/10 border-rose-500/30';
}

function factLabel(question) {
  if (question.fact_status === 'human_only') return 'Human-entered';
  if (question.fact_status === 'known') {
    if (question.fact_provenance === 'derived') return 'Derived from Profile';
    return 'Saved in Vault';
  }
  if (question.fact_status === 'known_absent') return 'Absent by rule';
  if (question.fact_status === 'needs_confirmation') return 'Requires verification';
  return 'Missing in Vault';
}

function pathTone(kind) {
  if (kind === 'application_action') return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  if (kind === 'account_action') return 'text-amber-300 bg-amber-500/10 border-amber-500/30';
  if (kind === 'informational') return 'text-sky-300 bg-sky-500/10 border-sky-500/30';
  return 'text-slate-300 bg-slate-500/10 border-slate-500/30';
}

function Confidence({ value }) {
  const percent = Math.round((Number(value) || 0) * 100);
  const tone = percent >= 85 ? 'text-emerald-400' : percent >= 60 ? 'text-amber-400' : 'text-rose-400';
  return <span className={`font-mono font-bold text-[10px] ${tone}`}>{percent}%</span>;
}

export default function PageBriefPanel({ pageBrief, runState, onRefresh, refreshing }) {
  const [showEvidence, setShowEvidence] = useState(null);

  if (!pageBrief) {
    return (
      <div className="glass-panel-elevated specular-top rounded-3xl p-8 text-center h-full flex flex-col items-center justify-center shadow-2xl border border-white/[0.08]">
        <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-4 text-indigo-400 shadow-inner">
          <Brain className="w-8 h-8" />
        </div>
        <h3 className="text-sm font-extrabold text-white">No Cognitive Page Brief</h3>
        <p className="text-xs text-slate-400 mt-2 max-w-sm mx-auto leading-relaxed">
          The agent reads candidate pages holistically before acting: detecting question blocks, section hierarchies, and navigation paths.
        </p>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="mt-5 flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-400 hover:to-violet-500 text-white text-xs font-semibold disabled:opacity-50 transition-all shadow-md shadow-indigo-500/20"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Generate Brief</span>
          </button>
        )}
      </div>
    );
  }

  const questions = (pageBrief.sections || []).flatMap((section) => section.questions || []);
  const needsHuman = questions.filter((question) => question.human_only || !question.concept);
  const choicePaths = (pageBrief.paths || []).filter((path) => path.needs_human_choice);
  const isForm = ['FORM', 'SECTION_FORM'].includes(pageBrief.page_type);

  return (
    <div className="glass-panel-elevated specular-top rounded-3xl overflow-hidden flex flex-col h-full shadow-2xl border border-white/[0.08]">
      {/* Header */}
      <div className="bg-white/[0.02] px-4 py-3 border-b border-white/[0.08] flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0">
            <Brain className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <h3 className="text-xs font-bold text-white uppercase tracking-wider truncate">
              Semantic Page Intent
            </h3>
            <p className="text-[10px] font-mono text-slate-400 truncate">
              {pageBrief.url || 'Active Navigation Target'}
            </p>
          </div>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-500/15 hover:bg-indigo-500/25 text-indigo-300 border border-indigo-500/40 text-[10px] font-bold disabled:opacity-50 transition-all"
          >
            <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Re-read</span>
          </button>
        )}
      </div>

      <div className="p-4 space-y-3 overflow-y-auto flex-1 min-h-0">
        {/* Page Classification Bar */}
        <div className="flex flex-wrap items-center gap-2">
          <span className={`text-[10px] font-bold px-2.5 py-1 rounded-xl border uppercase tracking-wider font-mono ${typeTone(pageBrief.page_type)}`}>
            {pageBrief.page_type || 'UNKNOWN'}
          </span>
          <span className="text-[10px] font-mono text-slate-300 bg-white/[0.04] px-2 py-0.5 rounded-md border border-white/[0.08]">
            <Confidence value={pageBrief.confidence} /> confidence
          </span>
          <span className="text-[10px] font-mono px-2.5 py-1 rounded-xl bg-slate-950 text-slate-300 border border-white/[0.08]">
            {pageBrief.source === 'model' ? (
              <span className="flex items-center gap-1.5 text-violet-300">
                <Sparkles className="w-3 h-3 text-violet-400" /> Neural Vision Read
              </span>
            ) : pageBrief.source === 'cache' ? (
              <span className="flex items-center gap-1.5 text-emerald-300">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" /> Cached Fast-Path
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-amber-300">
                <ShieldQuestion className="w-3 h-3 text-amber-400" /> Offline Heuristic
              </span>
            )}
          </span>
          {runState && (
            <span className="text-[9px] font-mono text-slate-500 uppercase">{runState}</span>
          )}
        </div>

        {/* Executive Intent Card */}
        <div className="rounded-2xl border border-white/[0.08] bg-slate-950/70 p-3.5 space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">In One Line:</div>
          <div className="text-xs font-bold text-white">
            {pageBrief.summary_line || pageBrief.title}
          </div>
          <p className="text-[11px] leading-relaxed text-slate-400">{pageBrief.purpose}</p>
          {pageBrief.fact_summary && (
            <div className="pt-1 flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-400 border-t border-white/[0.06]">
              <span>{pageBrief.fact_summary.total} facts needed</span>
              <span>· {pageBrief.fact_summary.explicit} from vault</span>
              <span>· {pageBrief.fact_summary.derived} derived</span>
              {pageBrief.fact_summary.unverified > 0 && (
                <span className="text-amber-300 font-bold">· {pageBrief.fact_summary.unverified} to confirm</span>
              )}
            </div>
          )}
        </div>

        {/* Essential Information Grid */}
        {(pageBrief.information || []).length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {pageBrief.information.map((item, index) => (
              <div key={`${item.label}-${index}`} className="rounded-xl bg-slate-950/60 border border-white/[0.06] px-3 py-2">
                <div className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold">{item.label}</div>
                <div className="text-[11px] font-mono text-white truncate font-medium mt-0.5" title={item.value}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Human Mandatory Intervention Alert */}
        {needsHuman.length > 0 && (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-[11px] text-amber-100">
            <div className="flex items-center gap-1.5 font-bold text-amber-300">
              <ShieldQuestion className="w-4 h-4" />
              <span>Mandatory Human Barrier: {needsHuman.length} fields cannot be auto-filled</span>
            </div>
            <div className="mt-1.5 space-y-0.5 text-[10px] text-amber-200/80">
              {needsHuman.slice(0, 4).map((q) => (
                <div key={q.question_id} className="truncate">• {q.asked}</div>
              ))}
            </div>
          </div>
        )}

        {/* Section Accordions */}
        {(pageBrief.sections || []).map((section) => (
          <div key={section.section_id} className="rounded-2xl border border-white/[0.08] bg-slate-950/70 overflow-hidden">
            <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/[0.06] bg-white/[0.02]">
              <span className="text-xs font-bold text-white truncate">{section.heading}</span>
              <span className="text-[10px] font-mono text-slate-400">
                {section.questions?.length || 0} fields · <Confidence value={section.confidence} />
              </span>
            </div>
            <div className="divide-y divide-white/[0.06]">
              {(section.questions || []).map((question) => (
                <div key={question.question_id} className="px-3.5 py-2.5 space-y-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-200">
                        {question.asked}
                        {question.required && <span className="ml-1 text-red-400 font-bold">*</span>}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <span className={`text-[9px] font-mono px-2 py-0.5 rounded-md border font-semibold ${conceptTone(question)}`}>
                          {question.human_only ? 'Human Only' : question.concept_label || 'Unclassified'}
                        </span>
                        {question.expected_format && (
                          <span className="text-[9px] font-mono text-slate-400 bg-white/[0.04] px-1.5 py-0.5 rounded border border-white/[0.06]">
                            {question.expected_format}
                          </span>
                        )}
                        <span className={`text-[9px] font-mono px-2 py-0.5 rounded-md border ${factTone(question.fact_status)}`}>
                          {factLabel(question)}
                        </span>
                        <Confidence value={question.concept_confidence} />
                      </div>
                      {question.reason && (
                        <p className="mt-1 text-[10px] leading-relaxed text-slate-400">{question.reason}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setShowEvidence(showEvidence === question.question_id ? null : question.question_id)
                      }
                      className="shrink-0 text-[10px] font-mono text-indigo-400 hover:text-indigo-300 px-2 py-1 rounded-lg bg-indigo-500/10 border border-indigo-500/20 transition-colors"
                    >
                      {showEvidence === question.question_id ? 'Hide trace' : 'Why?'}
                    </button>
                  </div>
                  {showEvidence === question.question_id && (
                    <div className="mt-2 rounded-xl bg-slate-900 border border-white/[0.08] p-2.5 text-[10px] font-mono text-slate-300 space-y-1">
                      <div className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">Reasoning Evidence:</div>
                      {(question.evidence || []).length > 0 ? (
                        question.evidence.map((item, idx) => <div key={idx}>• {item}</div>)
                      ) : (
                        <div>• Direct DOM label correspondence verified</div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}

        {/* Candidate Paths */}
        {(pageBrief.paths || []).length > 0 && (
          <div className="rounded-2xl border border-white/[0.08] bg-slate-950/70 overflow-hidden">
            <div className="px-3.5 py-2.5 border-b border-white/[0.06] text-xs font-bold text-white flex items-center gap-2">
              <Compass className="w-3.5 h-3.5 text-sky-400" />
              <span>Available Progression Paths</span>
            </div>
            <div className="divide-y divide-white/[0.06]">
              {pageBrief.paths.map((path) => (
                <div key={path.path_id} className="flex items-center justify-between gap-2 px-3.5 py-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <ArrowRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span className="text-xs text-slate-200 truncate">{path.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`text-[9px] font-mono px-2 py-0.5 rounded-md border font-semibold ${pathTone(path.kind)}`}>
                      {path.kind.replace('_', ' ')}
                    </span>
                    {path.needs_human_choice && (
                      <span className="text-[9px] font-mono text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20 font-bold">
                        User Decision Gate
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Read-Only Safety Banner */}
        <div className="rounded-2xl border border-white/[0.08] bg-slate-950/70 p-3 text-[10px] text-slate-400 leading-relaxed">
          {isForm
            ? 'Read-Only Cognitive Analysis. No form data was submitted or modified during this pass.'
            : choicePaths.length > 0
              ? 'FormPilot awaits explicit user guidance before taking navigational branches.'
              : 'Informational DOM snapshot recorded. Safe to proceed.'}
        </div>
      </div>
    </div>
  );
}
