import React, { useEffect, useState } from 'react';
import {
  Eye,
  ExternalLink,
  Play,
  ScanSearch,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  HelpCircle,
} from 'lucide-react';

const DEFAULT_QUERY = 'http://127.0.0.1:8000/gov-portal-demo';
const LAST_QUERY_KEY = 'formpilot.lastQuery';

function readSavedQuery() {
  try {
    return window.localStorage.getItem(LAST_QUERY_KEY) || DEFAULT_QUERY;
  } catch {
    return DEFAULT_QUERY;
  }
}

function saveQuery(value) {
  try {
    window.localStorage.setItem(LAST_QUERY_KEY, value);
  } catch {
    // A private window can block storage; the field still works for this tab.
  }
}

export default function PortalLauncher({ onLaunch, agentRunning, sessionOpen }) {
  const [query, setQuery] = useState(readSavedQuery);
  const [oracleResult, setOracleResult] = useState(null);
  const [loadingOracle, setLoadingOracle] = useState(false);
  const [runMode, setRunMode] = useState('fill');

  const updateQuery = (value) => {
    setQuery(value);
    saveQuery(value);
  };

  useEffect(() => {
    if (!query || query.trim().length < 2) {
      setOracleResult(null);
      return;
    }
    const timer = setTimeout(async () => {
      setLoadingOracle(true);
      try {
        const res = await fetch(`/api/oracle/search?q=${encodeURIComponent(query.trim())}`);
        if (res.ok) {
          const data = await res.json();
          setOracleResult(data);
        }
      } catch (err) {
        console.error('Portal lookup error:', err);
      } finally {
        setLoadingOracle(false);
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [query]);

  const quickPills = [
    {
      label: 'Practice portal',
      val: 'http://127.0.0.1:8000/gov-portal-demo',
      desc: 'Try a full multi-step application safely. No real submission or payment.',
    },
    {
      label: 'Practice sign-in',
      val: 'http://127.0.0.1:8000/gov-portal-demo',
      desc: 'Try the returning-candidate sign-in flow with the demo account.',
    },
    {
      label: 'Railway RRB',
      val: 'apply for railway',
      desc: 'Official RRB application portal',
    },
    {
      label: 'SSC',
      val: 'ssc cgl',
      desc: 'Official Staff Selection Commission portal',
    },
    {
      label: 'BPSC Bihar',
      val: 'bpsc bihar',
      desc: 'Official Bihar Public Service Commission portal',
    },
    {
      label: 'UPSC',
      val: 'upsc',
      desc: 'Official UPSC online application portal',
    },
  ];

  const handleApply = (event) => {
    event?.preventDefault();
    if (!query.trim() || agentRunning) return;
    saveQuery(query.trim());
    onLaunch(query.trim(), runMode);
  };

  const inspect = runMode === 'inspect';

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(245,158,11,0.14),transparent_48%),radial-gradient(ellipse_at_bottom_right,rgba(14,165,233,0.08),transparent_45%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-400/50 to-transparent" />

      <div className="relative grid gap-6 p-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:p-7">
        <div className="flex flex-col justify-center">
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/10">
              <Sparkles className="h-3.5 w-3.5 text-amber-400" />
            </span>
            <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-amber-400/90">
              Guided application workspace
            </span>
          </div>
          <h2 className="max-w-md text-2xl font-extrabold leading-tight tracking-tight text-white md:text-[28px]">
            Your details, in the right fields.
            <span className="block text-slate-400">Every step, with you in control.</span>
          </h2>
          <p className="mt-3 max-w-md text-xs leading-relaxed text-slate-400">
            FormPilot opens the real portal, fills from your saved profile, and asks whenever a
            value is unknown. CAPTCHA, OTP, photos, payment and final submission stay in your hands.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="flex items-center gap-1.5 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] font-semibold text-emerald-300">
              <UserCheck className="h-3 w-3" /> Profile-aware
            </span>
            <span className="flex items-center gap-1.5 rounded-lg border border-sky-500/25 bg-sky-500/10 px-2.5 py-1.5 text-[10px] font-semibold text-sky-300">
              <HelpCircle className="h-3 w-3" /> Asks when unsure
            </span>
            <span className="flex items-center gap-1.5 rounded-lg border border-amber-500/25 bg-amber-500/10 px-2.5 py-1.5 text-[10px] font-semibold text-amber-300">
              <ShieldCheck className="h-3 w-3" /> Never auto-submits
            </span>
          </div>
        </div>

        <div className="min-w-0">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
              Official portal or exam name
            </span>
            <span className="text-[10px] text-slate-500">
              {loadingOracle ? 'Checking official link…' : 'Official domains checked first'}
            </span>
          </div>

          <form onSubmit={handleApply} className="space-y-2.5">
            <div className="relative">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5">
                <Search className="h-4 w-4 text-slate-500" />
              </div>
              <input
                type="text"
                value={query}
                onChange={(event) => updateQuery(event.target.value)}
                disabled={agentRunning}
                placeholder="Paste the official link or type an exam name"
                className="w-full rounded-xl border border-slate-700/80 bg-slate-950 py-3 pl-10 pr-4 text-sm font-medium text-slate-100 outline-none transition-all placeholder:text-slate-500 focus:border-amber-500 focus:ring-1 focus:ring-amber-500/50 disabled:opacity-50"
              />
            </div>

            <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
              <div className="flex rounded-xl border border-slate-700 bg-slate-950 p-1">
                <button
                  type="button"
                  onClick={() => setRunMode('fill')}
                  disabled={agentRunning}
                  className={`flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-[11px] font-bold transition-all ${
                    !inspect
                      ? 'border border-amber-500/40 bg-amber-500/20 text-amber-300'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Fill with the agent, stopping for review, CAPTCHA, OTP, uploads, payment and submission."
                >
                  <Play className="h-3 w-3" />
                  Fill with me
                </button>
                <button
                  type="button"
                  onClick={() => setRunMode('inspect')}
                  disabled={agentRunning}
                  className={`flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-[11px] font-bold transition-all ${
                    inspect
                      ? 'border border-sky-500/40 bg-sky-500/20 text-sky-300'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Open the real portal and only scan it. Nothing is filled, clicked, paid or submitted."
                >
                  <ScanSearch className="h-3 w-3" />
                  Inspect only
                </button>
              </div>

              <button
                type="submit"
                disabled={agentRunning || !query.trim()}
                className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-extrabold shadow-lg transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${
                  inspect
                    ? 'bg-gradient-to-r from-sky-500 via-cyan-500 to-sky-600 text-slate-950 shadow-sky-500/20 hover:from-sky-400 hover:to-cyan-500'
                    : 'bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 text-slate-950 shadow-amber-500/20 hover:from-amber-400 hover:to-orange-500'
                }`}
              >
                {inspect ? <Eye className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}
                <span>
                  {agentRunning
                    ? 'Starting…'
                    : inspect
                      ? 'Open inspect-only'
                      : sessionOpen
                        ? 'Start new application'
                        : 'Start application'}
                </span>
              </button>
            </div>
          </form>

          <div className={`mt-2.5 rounded-lg border px-3 py-2 text-[11px] leading-relaxed ${
            inspect
              ? 'border-sky-500/30 bg-sky-500/10 text-sky-200'
              : 'border-slate-800 bg-slate-950/60 text-slate-500'
          }`}>
            {inspect
              ? 'Inspect-only: FormPilot opens the real page, maps its fields and selectors, and stops. Nothing is filled, clicked, paid or submitted.'
              : 'Fill with review: the agent fills from your profile, pauses for anything it cannot know, and stops before payment or final submission.'}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Try
            </span>
            {quickPills.map((pill, index) => (
              <button
                key={index}
                type="button"
                disabled={agentRunning}
                onClick={() => updateQuery(pill.val)}
                className={`rounded-lg border px-2 py-1 text-[10px] transition-all ${
                  query === pill.val
                    ? 'border-amber-500/50 bg-amber-500/20 font-semibold text-amber-300'
                    : 'border-slate-700/80 bg-slate-800/60 text-slate-300 hover:bg-slate-800'
                }`}
                title={pill.desc}
              >
                {pill.label}
              </button>
            ))}
          </div>

          {oracleResult && (
            <div className="animate-fadeIn mt-3 flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3">
              <div className="flex items-start gap-3">
                <div
                  className={`mt-0.5 rounded-lg p-2 ${
                    oracleResult.is_practice
                      ? 'bg-sky-500/10 text-sky-400'
                      : oracleResult.is_gov_domain
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-amber-500/10 text-amber-400'
                  }`}
                >
                  {oracleResult.is_practice ? (
                    <Sparkles className="h-5 w-5" />
                  ) : oracleResult.is_gov_domain ? (
                    <ShieldCheck className="h-5 w-5" />
                  ) : (
                    <ShieldAlert className="h-5 w-5" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-bold text-slate-200">
                      {oracleResult.official_name}
                    </span>
                    <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[9px] font-bold text-slate-300">
                      {oracleResult.authority_type}
                    </span>
                    {oracleResult.is_practice ? (
                      <span className="rounded border border-sky-500/30 bg-sky-950/50 px-1.5 py-0.5 font-mono text-[9px] text-sky-400">
                        Practice portal
                      </span>
                    ) : oracleResult.is_gov_domain ? (
                      <span className="rounded border border-emerald-500/30 bg-emerald-950/50 px-1.5 py-0.5 font-mono text-[9px] text-emerald-400">
                        Official domain
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 break-all font-mono text-[10px] text-slate-500">
                    {oracleResult.target_url}
                  </p>
                  <p
                    className={`mt-1 text-[10px] leading-relaxed ${
                      oracleResult.is_practice ? 'text-sky-300/90' : 'text-amber-300/90'
                    }`}
                  >
                    {oracleResult.advisory}
                  </p>
                </div>
                <a
                  href={oracleResult.target_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-[10px] font-medium text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
                >
                  <span className="hidden sm:inline">Open portal</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
