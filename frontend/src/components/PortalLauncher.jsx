import React, { useState, useEffect } from 'react';
import { Search, ShieldAlert, ShieldCheck, ExternalLink, Play, Sparkles } from 'lucide-react';

export default function PortalLauncher({ onLaunch, agentRunning }) {
  const [query, setQuery] = useState('http://127.0.0.1:8000/gov-portal-demo');
  const [oracleResult, setOracleResult] = useState(null);
  const [loadingOracle, setLoadingOracle] = useState(false);

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

  const handleApply = (e) => {
    e?.preventDefault();
    if (!query.trim() || agentRunning) return;
    onLaunch(query.trim());
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden">
      <div className="absolute top-0 right-0 w-80 h-40 bg-gradient-to-bl from-amber-500/10 via-orange-500/5 to-transparent pointer-events-none rounded-2xl" />

      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-400" />
          <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wide">
            Find your application portal
          </h2>
        </div>
        <span className="text-xs text-slate-400">
          {loadingOracle ? 'Checking the official link…' : 'Official domains checked first'}
        </span>
      </div>

      <form onSubmit={handleApply} className="flex gap-2">
        <div className="relative flex-1">
          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
            <Search className="w-4 h-4 text-slate-400" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={agentRunning}
            placeholder="Type an exam name (for example, 'railway ntpc') or paste the official portal link"
            className="w-full pl-10 pr-4 py-3 rounded-xl bg-slate-950 border border-slate-700/80 focus:border-amber-500 focus:ring-1 focus:ring-amber-500/50 text-slate-100 placeholder-slate-500 text-sm font-medium outline-none transition-all disabled:opacity-50"
          />
        </div>

        <button
          type="submit"
          disabled={agentRunning || !query.trim()}
          className="px-6 py-3 rounded-xl bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:from-amber-400 hover:to-orange-500 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg shadow-amber-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
        >
          <Play className="w-4 h-4 fill-current" />
          <span>{agentRunning ? 'Starting…' : 'Start application'}</span>
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-slate-800/80">
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
          Quick links:
        </span>
        {quickPills.map((p, i) => (
          <button
            key={i}
            type="button"
            disabled={agentRunning}
            onClick={() => setQuery(p.val)}
            className={`text-xs px-2.5 py-1 rounded-lg border transition-all ${
              query === p.val
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 font-semibold'
                : 'bg-slate-800/60 hover:bg-slate-800 text-slate-300 border-slate-700/80'
            }`}
            title={p.desc}
          >
            {p.label}
          </button>
        ))}
      </div>

      {oracleResult && (
        <div className="mt-4 p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3 animate-fadeIn">
          <div className="flex items-start gap-3">
            <div
              className={`p-2 rounded-lg mt-0.5 ${
                oracleResult.is_gov_domain
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : 'bg-amber-500/10 text-amber-400'
              }`}
            >
              {oracleResult.is_gov_domain ? (
                <ShieldCheck className="w-5 h-5" />
              ) : (
                <ShieldAlert className="w-5 h-5" />
              )}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-slate-200">
                  {oracleResult.official_name}
                </span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">
                  {oracleResult.authority_type}
                </span>
                {oracleResult.is_gov_domain && (
                  <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/50 px-1.5 py-0.5 rounded border border-emerald-500/30">
                    Official domain
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-1 flex items-center gap-1 font-mono break-all">
                <span>{oracleResult.target_url}</span>
              </p>
              <p className="text-xs text-amber-300/90 mt-1">
                {oracleResult.advisory}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-end md:self-center shrink-0">
            <a
              href={oracleResult.target_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-slate-400 hover:text-slate-200 flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors"
            >
              <span>Open portal</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
