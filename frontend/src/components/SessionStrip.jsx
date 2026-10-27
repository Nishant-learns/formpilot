import React from 'react';
import {
  Check,
  ChevronRight,
  ClipboardList,
  Download,
  FileText,
  Globe2,
  Lock,
  Pause,
  Play,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from 'lucide-react';

const ACTIVE_STATES = new Set([
  'RESOLVING',
  'RUNNING',
  'WAITING_FOR_USER',
  'PAUSED',
  'INSPECT_READY',
]);

function metricPill(label, value, tone = 'text-slate-200') {
  return (
    <div className="flex min-w-[74px] flex-col rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-1.5">
      <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        {label}
      </span>
      <span className={`font-mono text-xs font-bold ${tone}`}>{value}</span>
    </div>
  );
}

function stepState(done, active, locked) {
  if (done) return 'done';
  if (active) return 'active';
  if (locked) return 'locked';
  return 'pending';
}

function Step({ icon: Icon, label, detail, state, last }) {
  const styles = {
    done: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
    active: 'border-amber-400/60 bg-amber-500/15 text-amber-200 shadow-[0_0_0_3px_rgba(245,158,11,0.08)]',
    pending: 'border-slate-700/70 bg-slate-950/60 text-slate-500',
    locked: 'border-slate-800 bg-slate-950/40 text-slate-600',
  };
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border ${styles[state]}`}>
        {state === 'done' ? <Check className="h-4 w-4" /> : state === 'locked' ? <Lock className="h-3.5 w-3.5" /> : <Icon className="h-4 w-4" />}
      </div>
      <div className="min-w-0">
        <div className={`truncate text-[11px] font-bold ${state === 'active' ? 'text-amber-200' : state === 'done' ? 'text-emerald-200' : 'text-slate-400'}`}>
          {label}
        </div>
        <div className="truncate text-[9px] text-slate-500">{detail}</div>
      </div>
      {!last && <ChevronRight className="ml-auto hidden h-3.5 w-3.5 shrink-0 text-slate-700 sm:block" />}
    </div>
  );
}

export default function SessionStrip({
  runState,
  runMode,
  currentSection,
  formMap,
  recipe,
  readiness,
  query,
  targetUrl,
  elapsed,
  paused,
  runId,
  fillSummary,
  entryMode,
  loginMethod,
  onPauseToggle,
  onNewSession,
}) {
  const inspect = runMode === 'inspect';
  const busy = ACTIVE_STATES.has(runState);
  const waiting = runState === 'WAITING_FOR_USER';
  const finished = ['AWAITING_PAYMENT', 'COMPLETED', 'STOPPED', 'FAILED'].includes(runState);
  const canRestart = ['STOPPED', 'FAILED', 'COMPLETED'].includes(runState);
  const auditAvailable = ['AWAITING_PAYMENT', 'COMPLETED'].includes(runState);
  const fields = formMap?.field_count || 0;
  const gateways = formMap?.gateways?.length || 0;
  const known = formMap?.known_field_count || 0;
  const humanOnly = formMap?.human_field_count || 0;
  const recipeStatus = recipe?.status || 'new';
  const recipeLabel = recipeStatus === 'match'
    ? `v${recipe?.version || 1} matched`
    : recipeStatus === 'drift'
      ? 'Structure changed'
      : 'New page';

  const portalDone = Boolean(formMap || targetUrl);
  const fillStatus = fillSummary?.status || '';
  const fillVerified = Number(fillSummary?.verified || 0);
  const fillAttempted = Number(fillSummary?.attempted || 0);
  const fillFailed = Number(fillSummary?.failed || 0);
  const fillSkipped = Number(fillSummary?.skipped || 0);
  const fillSettled = ['FILLED', 'NO_FIELDS'].includes(fillStatus);
  const fillActive = !inspect && !waiting && !finished && (runState === 'RUNNING' || runState === 'PAUSED' || runState === 'RESOLVING');
  // A section is only "filled" when the backend verified the values on the
  // portal.  Waiting for the human is not evidence that the page is filled.
  const fillDone = !inspect && (fillSettled || ['AWAITING_PAYMENT', 'COMPLETED'].includes(runState));
  const fillDetail = inspect
    ? `${fields} field${fields === 1 ? '' : 's'}${gateways ? ` · ${gateways} gateway${gateways === 1 ? '' : 's'}` : ''} mapped`
    : fillStatus === 'FILLED'
      ? `${fillVerified} of ${fillAttempted} fields verified`
      : fillStatus === 'PARTIAL'
        ? `${fillVerified} verified · ${fillFailed} failed · ${fillSkipped} skipped`
        : fillStatus === 'FAILED'
          ? `Fill failed · 0 of ${fillAttempted} verified`
          : fillStatus === 'NO_FIELDS'
            ? 'No fillable fields on this page'
            : `${known} of ${fields || '—'} fields matched`;
  const checksActive = waiting;
  const checksDone = !inspect && ['AWAITING_PAYMENT', 'COMPLETED'].includes(runState);
  const reviewActive = runState === 'AWAITING_PAYMENT';
  const reviewDone = runState === 'COMPLETED';
  const entryLabel = entryMode === 'register'
    ? 'Account creation'
    : entryMode === 'login'
      ? `Sign in${loginMethod ? ` · ${String(loginMethod).replace(/_/g, ' ')}` : ''}`
      : entryMode === 'resume'
        ? 'Resume application'
        : entryMode === 'manual'
          ? 'Chosen in browser'
          : '';

  const title = query || targetUrl || (inspect ? 'Inspect-only browser' : 'Application in progress');
  const stateLabel = paused
    ? 'Paused by you'
    : waiting
      ? 'Waiting for your input'
      : runState === 'AWAITING_PAYMENT'
        ? 'Ready for your review'
        : runState === 'INSPECT_READY'
          ? 'Inspection complete'
          : finished
            ? 'Session finished'
            : 'Agent working';

  return (
    <section className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 shadow-xl">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(245,158,11,0.12),transparent_55%)]" />
      <div className="relative flex flex-col gap-3 px-4 py-3.5 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${paused ? 'border-slate-700 bg-slate-800 text-slate-300' : 'border-amber-400/40 bg-amber-500/15 text-amber-300'}`}>
              {inspect ? <Globe2 className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />}
              {!paused && busy && (
                <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-slate-900 bg-emerald-400" />
              )}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.14em] ${
                  inspect
                    ? 'border-sky-500/40 bg-sky-500/10 text-sky-300'
                    : 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                }`}>
                  {inspect ? 'Inspect only' : paused ? 'Paused' : 'Guided fill'}
                </span>
                {!inspect && entryLabel && (
                  <span className="rounded-full border border-slate-700 bg-slate-800/70 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-300">
                    {entryLabel}
                  </span>
                )}
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                  {stateLabel}
                </span>
              </div>
              <div className="mt-0.5 truncate text-sm font-bold text-slate-100" title={title}>
                {title}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {metricPill('Fields', formMap ? `${known}/${fields}` : '—', formMap && known === fields ? 'text-emerald-300' : 'text-slate-200')}
            {metricPill('Human-only', humanOnly || 0, humanOnly ? 'text-sky-300' : 'text-slate-400')}
            {metricPill('Profile', readiness ? `${readiness.percent}%` : '—', readiness?.percent >= 80 ? 'text-emerald-300' : 'text-amber-300')}
            {metricPill('Recipe', recipeLabel, recipeStatus === 'match' ? 'text-emerald-300' : recipeStatus === 'drift' ? 'text-amber-300' : 'text-sky-300')}
            {metricPill('Elapsed', elapsed || '00:00', 'text-slate-300')}

            {!inspect && (runState === 'RUNNING' || runState === 'RESOLVING' || runState === 'PAUSED') && (
              <button
                type="button"
                onClick={onPauseToggle}
                className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 text-[11px] font-bold transition-colors ${
                  paused
                    ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25'
                    : 'border-slate-700 bg-slate-800/80 text-slate-200 hover:bg-slate-700'
                }`}
                title={paused ? 'Resume the application' : 'Pause the agent at the next safe point'}
              >
                {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
                <span>{paused ? 'Resume' : 'Pause'}</span>
              </button>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 overflow-x-auto border-t border-slate-800/70 pt-3 no-scrollbar">
          <Step
            icon={Globe2}
            label="Portal"
            detail={portalDone ? 'Page observed' : 'Opening the page'}
            state={stepState(portalDone, !portalDone, false)}
          />
          <Step
            icon={ClipboardList}
            label={inspect ? 'Page mapped' : `Details · Section ${currentSection || 1}`}
            detail={fillDetail}
            state={stepState(fillDone || (inspect && portalDone), fillActive, false)}
          />
          <Step
            icon={ShieldCheck}
            label="Human checks"
            detail={inspect ? 'Not used in inspect-only' : waiting ? 'Needs you now' : 'CAPTCHA · OTP · uploads'}
            state={stepState(checksDone, checksActive, false)}
          />
          <Step
            icon={UserCheck}
            label="Your review"
            detail={inspect ? 'Nothing was submitted' : waiting ? 'Approve each section' : 'You approve the final form'}
            state={stepState(reviewDone, reviewActive, !reviewActive && !reviewDone)}
          />
          <Step
            icon={Send}
            label="Payment & submit"
            detail="Always done by you"
            state={stepState(false, false, true)}
            last
          />
        </div>

        {(canRestart || auditAvailable) && (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-800/70 pt-2.5">
            {runId && (
              <a
                href={`/api/runs/${runId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/70 px-2.5 py-1.5 text-[10px] font-semibold text-slate-300 transition-colors hover:bg-slate-700"
                title="Open the recorded run journal"
              >
                <FileText className="h-3 w-3" />
                Run journal
              </a>
            )}
            {auditAvailable && runId && (
              <a
                href={`/api/runs/${runId}/audit`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] font-semibold text-emerald-300 transition-colors hover:bg-emerald-500/20"
                title="Download the audit report"
              >
                <Download className="h-3 w-3" />
                Audit JSON
              </a>
            )}
            {canRestart && (
              <button
                type="button"
                onClick={onNewSession}
                className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/15 px-3 py-1.5 text-[10px] font-bold text-amber-300 transition-colors hover:bg-amber-500/25"
              >
                <Plus className="h-3 w-3" />
                New application
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
