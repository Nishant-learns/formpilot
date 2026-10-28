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
} from 'lucide-react';

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

function pathTone(kind) {
  if (kind === 'application_action') return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  if (kind === 'account_action') return 'text-amber-300 bg-amber-500/10 border-amber-500/30';
  if (kind === 'informational') return 'text-sky-300 bg-sky-500/10 border-sky-500/30';
  return 'text-slate-300 bg-slate-500/10 border-slate-500/30';
}

function Confidence({ value }) {
  const percent = Math.round((Number(value) || 0) * 100);
  const tone = percent >= 85 ? 'text-emerald-300' : percent >= 60 ? 'text-amber-300' : 'text-rose-300';
  return <span className={`font-mono text-[10px] ${tone}`}>{percent}%</span>;
}

export default function PageBriefPanel({ pageBrief, runState, onRefresh, refreshing }) {
  const [showEvidence, setShowEvidence] = useState(null);

  if (!pageBrief) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center h-full min-h-[460px] flex flex-col items-center justify-center">
        <div className="w-14 h-14 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-center mb-3 text-slate-600">
          <FileText className="w-7 h-7" />
        </div>
        <h3 className="text-sm font-bold text-slate-300">No page brief yet</h3>
        <p className="text-xs text-slate-500 mt-2 max-w-sm mx-auto leading-relaxed">
          Open a portal in inspect mode. FormPilot reads the page like a person:
          headings, questions, groups and paths. Nothing is filled while the brief
          is being read.
        </p>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="mt-4 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 border border-sky-500/40 text-[11px] font-bold disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Read the page</span>
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
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden flex flex-col h-full min-h-[460px]">
      <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Brain className="w-4 h-4 text-sky-400 shrink-0" />
          <div className="min-w-0">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wide truncate">
              What this page wants
            </h3>
            <p className="text-[10px] font-mono text-slate-500 truncate">
              {pageBrief.url || 'unknown page'}
            </p>
          </div>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 border border-sky-500/40 text-[10px] font-bold disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Re-read</span>
          </button>
        )}
      </div>

      <div className="p-4 space-y-3 overflow-y-auto flex-1 min-h-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`text-[10px] font-bold px-2 py-1 rounded-lg border uppercase tracking-wider ${typeTone(pageBrief.page_type)}`}>
            {pageBrief.page_type || 'UNKNOWN'}
          </span>
          <span className="text-[10px] font-mono text-slate-400">
            <Confidence value={pageBrief.confidence} /> confidence
          </span>
          <span className="text-[10px] font-mono px-2 py-1 rounded-lg bg-slate-950 text-slate-400 border border-slate-800">
            {pageBrief.source === 'model' ? (
              <span className="flex items-center gap-1"><Sparkles className="w-3 h-3 text-violet-300" /> read by model</span>
            ) : pageBrief.source === 'cache' ? (
              <span className="flex items-center gap-1"><CheckCircle2 className="w-3 h-3 text-emerald-300" /> cached read</span>
            ) : (
              <span className="flex items-center gap-1"><ShieldQuestion className="w-3 h-3 text-amber-300" /> offline read</span>
            )}
          </span>
          {runState && (
            <span className="text-[9px] font-mono text-slate-600">{runState}</span>
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">In one line</div>
          <div className="mt-1 text-[12px] font-semibold text-slate-200">
            {pageBrief.summary_line || pageBrief.title}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{pageBrief.purpose}</p>
        </div>

        {(pageBrief.information || []).length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {pageBrief.information.map((item, index) => (
              <div key={`${item.label}-${index}`} className="rounded-xl bg-slate-950 border border-slate-800 px-3 py-2">
                <div className="text-[9px] uppercase tracking-wider text-slate-500">{item.label}</div>
                <div className="text-[11px] font-mono text-slate-200 truncate" title={item.value}>{item.value}</div>
              </div>
            ))}
          </div>
        )}

        {needsHuman.length > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100">
            <div className="flex items-center gap-1.5 font-bold">
              <ShieldQuestion className="w-3.5 h-3.5 text-amber-300" />
              Only you can answer {needsHuman.length} of these
            </div>
            <div className="mt-1 space-y-0.5 text-[10px] text-amber-200/80">
              {needsHuman.slice(0, 5).map((question) => (
                <div key={question.question_id} className="truncate">• {question.asked}</div>
              ))}
            </div>
          </div>
        )}

        {(pageBrief.sections || []).map((section) => (
          <div key={section.section_id} className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-slate-800">
              <span className="text-[11px] font-bold text-slate-200 truncate">{section.heading}</span>
              <span className="text-[10px] font-mono text-slate-500">
                {section.questions?.length || 0} questions · <Confidence value={section.confidence} />
              </span>
            </div>
            <div className="divide-y divide-slate-800/70">
              {(section.questions || []).map((question) => (
                <div key={question.question_id} className="px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold text-slate-200">
                        {question.asked}
                        {question.required && <span className="ml-1 text-rose-400">*</span>}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${conceptTone(question)}`}>
                          {question.human_only
                            ? 'human only'
                            : question.concept_label || 'meaning unknown'}
                        </span>
                        {question.expected_format && (
                          <span className="text-[9px] font-mono text-slate-500">
                            format {question.expected_format}
                          </span>
                        )}
                        {question.constraints?.confirmation && (
                          <span className="text-[9px] font-mono text-sky-400">confirmation</span>
                        )}
                        <Confidence value={question.concept_confidence} />
                      </div>
                      {question.reason && (
                        <div className="mt-1 text-[10px] leading-relaxed text-slate-500">{question.reason}</div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowEvidence(showEvidence === question.question_id ? null : question.question_id)}
                      className="shrink-0 text-[9px] font-mono text-slate-500 hover:text-sky-300"
                    >
                      {showEvidence === question.question_id ? 'hide' : 'why?'}
                    </button>
                  </div>
                  {showEvidence === question.question_id && (
                    <div className="mt-1.5 rounded-lg bg-slate-900 border border-slate-800 px-2 py-1.5 text-[9px] font-mono text-slate-400 space-y-0.5">
                      {(question.evidence || []).length > 0
                        ? question.evidence.map((item, index) => <div key={index}>• {item}</div>)
                        : <div>• no human-visible evidence</div>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}

        {(pageBrief.paths || []).length > 0 && (
          <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-800 text-[11px] font-bold text-slate-200">
              Paths on this page
            </div>
            <div className="divide-y divide-slate-800/70">
              {pageBrief.paths.map((path) => (
                <div key={path.path_id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <ArrowRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <span className="text-[11px] text-slate-200 truncate">{path.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${pathTone(path.kind)}`}>
                      {path.kind.replace('_', ' ')}
                    </span>
                    {path.needs_human_choice && (
                      <span className="text-[9px] font-mono text-amber-300">your choice</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {(pageBrief.ambiguities || []).length > 0 && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100">
            <div className="flex items-center gap-1.5 font-bold">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-300" />
              {pageBrief.ambiguities.length} thing{pageBrief.ambiguities.length === 1 ? '' : 's'} to confirm
            </div>
            <div className="mt-1 space-y-1 text-[10px] leading-relaxed text-amber-200/85">
              {pageBrief.ambiguities.map((item) => (
                <div key={item.ambiguity_id}>• {item.description}</div>
              ))}
            </div>
          </div>
        )}

        {(pageBrief.human_only || []).length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="flex items-center gap-1 text-[9px] font-mono uppercase tracking-wider text-slate-500">
              <Lock className="w-3 h-3" /> always human
            </span>
            {pageBrief.human_only.map((item) => (
              <span key={item} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-400">
                {item.replace('_', ' ')}
              </span>
            ))}
          </div>
        )}

        <div className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-[10px] text-slate-500 leading-relaxed">
          {isForm
            ? 'This is a read-only brief. No value has been typed and no button has been pressed.'
            : choicePaths.length > 0
              ? 'FormPilot will ask you to choose a path before it acts. It will not guess.'
              : 'This page is understood as information. FormPilot will not invent a next step.'}
        </div>
      </div>
    </div>
  );
}
