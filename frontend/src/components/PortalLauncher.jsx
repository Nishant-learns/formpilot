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
  X,
  Compass,
  CheckCircle2,
} from 'lucide-react';
import { PRACTICE_PORTAL_URL } from '../apiConfig';
import {
  GovEmblemIcon,
  UPSCSealIcon,
  SSCSealIcon,
  RailwaySealIcon,
  NeuralSparkleIcon,
  SecurityShieldIcon,
} from './CustomIcons';

const LIVE_TEST_PORTAL_URL = PRACTICE_PORTAL_URL;
const DEFAULT_QUERY = LIVE_TEST_PORTAL_URL;
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
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  const quickPills = [
    {
      label: 'Practice Portal',
      val: LIVE_TEST_PORTAL_URL,
      isPractice: true,
      icon: NeuralSparkleIcon,
      desc: 'Safe recruitment sandbox for testing (4 steps, demo OTP & mock CAPTCHA).',
    },
    {
      label: 'Railway RRB',
      val: 'apply for railway',
      icon: RailwaySealIcon,
      desc: 'Official RRB application portal (Ministry of Railways)',
    },
    {
      label: 'SSC CGL',
      val: 'ssc cgl',
      icon: SSCSealIcon,
      desc: 'Staff Selection Commission (Govt of India)',
    },
    {
      label: 'UPSC Online',
      val: 'upsc',
      icon: UPSCSealIcon,
      desc: 'Union Public Service Commission civil services portal',
    },
    {
      label: 'BPSC Bihar',
      val: 'bpsc bihar',
      icon: GovEmblemIcon,
      desc: 'Bihar Public Service Commission application portal',
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
    <div className="glass-panel specular-top relative overflow-hidden rounded-2xl shadow-2xl transition-all">
      <div className="p-4 sm:p-5">
        {/* Top utility row: Status tag + Practice Portal quick pill */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg border border-indigo-500/30 bg-indigo-500/10 text-indigo-400">
              <Compass className="h-3.5 w-3.5" />
            </span>
            <span className="text-xs font-extrabold tracking-wide text-slate-200">
              Target Portal Omnibox
            </span>
            <span className="hidden sm:inline text-[11px] text-slate-600">•</span>
            <span className="hidden sm:inline text-[11px] text-slate-400">
              {loadingOracle ? 'Verifying official domain…' : 'Official government links verified automatically'}
            </span>
          </div>

          {/* Test portal instant access pill */}
          <div className="flex items-center gap-1.5 rounded-xl border border-emerald-500/30 bg-emerald-950/40 px-3 py-1 text-xs shadow-sm">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold text-emerald-300">Test Portal:</span>
            <button
              type="button"
              onClick={() => updateQuery(LIVE_TEST_PORTAL_URL)}
              className="font-bold text-sky-400 hover:text-sky-300 transition-colors underline decoration-sky-500/40 underline-offset-2 ml-1"
            >
              Load Demo
            </button>
            <span className="text-slate-600">|</span>
            <a
              href={LIVE_TEST_PORTAL_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-0.5 text-[11px] text-slate-400 hover:text-slate-200"
              title="Open Mock Portal in new tab"
            >
              Live Site <ExternalLink className="h-2.5 w-2.5" />
            </a>
          </div>
        </div>

        {/* Primary Input & Actions */}
        <form onSubmit={handleApply} className="space-y-3">
          <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
            {/* Search Input */}
            <div className="relative min-w-0 flex-1">
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5">
                <Search className="h-4 w-4 text-slate-400" />
              </div>
              <input
                type="text"
                value={query}
                onChange={(e) => updateQuery(e.target.value)}
                disabled={agentRunning}
                placeholder="Enter official portal URL or exam name (e.g. SSC CGL, RRB NTPC, UPSC)..."
                className="w-full rounded-xl glass-input py-2.5 pl-10 pr-9 text-xs sm:text-sm font-medium text-slate-100 outline-none transition-all placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/40 disabled:opacity-50"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => updateQuery('')}
                  disabled={agentRunning}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-200 transition-colors"
                  title="Clear input"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Mode Switcher */}
            <div className="flex shrink-0 rounded-xl border border-white/[0.08] bg-black/40 p-1">
              <button
                type="button"
                onClick={() => setRunMode('fill')}
                disabled={agentRunning}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                  !inspect
                    ? 'border border-indigo-500/40 bg-indigo-500/20 text-indigo-200 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Fill with guided review, pausing for CAPTCHA, OTP, and final payment."
              >
                <Play className="h-3.5 w-3.5" />
                <span>Auto-Fill</span>
              </button>
              <button
                type="button"
                onClick={() => setRunMode('inspect')}
                disabled={agentRunning}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                  inspect
                    ? 'border border-sky-500/40 bg-sky-500/20 text-sky-200 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Scan and map form structure without filling, clicking, or submitting."
              >
                <ScanSearch className="h-3.5 w-3.5" />
                <span>Inspect</span>
              </button>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={agentRunning || !query.trim()}
              className={`flex shrink-0 items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-xs sm:text-sm font-semibold shadow-lg transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${
                inspect
                  ? 'bg-gradient-to-r from-sky-500 to-cyan-500 text-slate-950 shadow-sky-500/20 hover:from-sky-400 hover:to-cyan-400'
                  : 'bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 text-white shadow-indigo-500/25 hover:from-indigo-400 hover:to-violet-500'
              }`}
            >
              {inspect ? <Eye className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}
              <span>
                {agentRunning
                  ? 'Launching…'
                  : inspect
                    ? 'Open & Map Page'
                    : sessionOpen
                      ? 'Start New Application'
                      : 'Launch Assistant ↵'}
              </span>
            </button>
          </div>
        </form>

        {/* Quick Select Pills */}
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mr-1">
            Quick Select:
          </span>
          {quickPills.map((pill, index) => {
            const isSelected = query === pill.val;
            const Icon = pill.icon;
            return (
              <button
                key={index}
                type="button"
                disabled={agentRunning}
                onClick={() => updateQuery(pill.val)}
                className={`flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all ${
                  isSelected
                    ? 'border-indigo-500/60 bg-indigo-500/25 text-indigo-200 shadow-sm'
                    : pill.isPractice
                      ? 'border-emerald-500/40 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-900/40'
                      : 'border-white/[0.08] bg-white/[0.03] text-slate-300 hover:border-white/[0.16] hover:bg-white/[0.06] hover:text-white'
                }`}
                title={pill.desc}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{pill.label}</span>
              </button>
            );
          })}
        </div>

        {/* Oracle Verification Result (Compact & High Trust) */}
        {oracleResult && (
          <div className="animate-fadeIn mt-3.5 rounded-xl glass-panel-elevated p-3 shadow-inner">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
              <div className="flex items-start sm:items-center gap-2.5 min-w-0">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${
                    oracleResult.is_practice
                      ? 'bg-sky-500/10 text-sky-400 border border-sky-500/30'
                      : oracleResult.is_gov_domain
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                  }`}
                >
                  {oracleResult.is_practice ? (
                    <Sparkles className="h-4 w-4" />
                  ) : oracleResult.is_gov_domain ? (
                    <SecurityShieldIcon className="h-4 w-4" />
                  ) : (
                    <ShieldAlert className="h-4 w-4" />
                  )}
                </div>

                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs font-bold text-slate-200 truncate">
                      {oracleResult.official_name}
                    </span>
                    <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] font-medium text-slate-300">
                      {oracleResult.authority_type}
                    </span>
                    {oracleResult.is_practice ? (
                      <span className="rounded-full border border-sky-500/30 bg-sky-950/60 px-2 py-0.5 text-[10px] font-bold text-sky-300">
                        Practice Sandbox
                      </span>
                    ) : oracleResult.is_gov_domain ? (
                      <span className="rounded-full border border-emerald-500/30 bg-emerald-950/60 px-2 py-0.5 text-[10px] font-bold text-emerald-300 flex items-center gap-1">
                        <CheckCircle2 className="h-2.5 w-2.5" /> Official Verified
                      </span>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="font-mono text-[10px] text-slate-400 truncate max-w-sm sm:max-w-md">
                      {oracleResult.target_url}
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="text-[10px] text-slate-400">
                      Trust: <span className="text-emerald-400 font-bold">{oracleResult.domain_trust_score}%</span>
                    </span>
                  </div>
                </div>
              </div>

              <a
                href={oracleResult.target_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-white/[0.08] hover:text-white"
              >
                <span>Visit Portal</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {oracleResult.advisory && (
              <div className="mt-2 pt-2 border-t border-white/[0.08] text-[11px] text-slate-300 flex items-center gap-2">
                <span className="text-amber-400 font-bold shrink-0">Note:</span>
                <span className="truncate">{oracleResult.advisory}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
