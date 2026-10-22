import React, { useState, useEffect } from 'react';
import { Search, ShieldAlert, ShieldCheck, ExternalLink, Play, Sparkles, Building2, Train, Compass } from 'lucide-react';

export default function PortalLauncher({ onLaunch, agentRunning }) {
  const [query, setQuery] = useState('http://127.0.0.1:8000/gov-portal-demo');
  const [oracleResult, setOracleResult] = useState(null);
  const [loadingOracle, setLoadingOracle] = useState(false);

  // Debounced oracle lookup
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
        console.error('Oracle lookup error:', err);
      } finally {
        setLoadingOracle(false);
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [query]);

  const quickPills = [
    {
      label: '🏛️ Gov Portal Simulator (CREB Demo)',
      val: 'http://127.0.0.1:8000/gov-portal-demo',
      desc: 'Test all 10 gates safely: Gateway, Missing APAAR, Biometrics, Captcha & Safety Lock'
    },
    {
      label: '🔑 Verify Existing OTR Login (Route 2)',
      val: 'http://127.0.0.1:8000/gov-portal-demo',
      desc: 'Test Route 2: Login with generated OTR ID & verify saved citizen profile'
    },
    {
      label: '🚂 Railway RRB (rrbapply.gov.in)',
      val: 'apply for railway',
      desc: 'RRB Central Recruitment Portal'
    },
    {
      label: '📋 SSC OTR (ssc.gov.in)',
      val: 'ssc cgl 2026',
      desc: 'Staff Selection Commission OTR'
    },
    {
      label: '🏢 BPSC Bihar (onlinebpsc.bihar.gov.in)',
      val: 'bpsc bihar',
      desc: 'Bihar Public Service Commission'
    },
    {
      label: '🎓 UPSC Civil Services (upsconline.nic.in)',
      val: 'upsc',
      desc: 'UPSC Online Portal'
    }
  ];

  const handleApply = (e) => {
    e?.preventDefault();
    if (!query.trim() || agentRunning) return;
    onLaunch(query.trim());
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden">
      {/* Background ambient glow */}
      <div className="absolute top-0 right-0 w-80 h-40 bg-gradient-to-bl from-amber-500/10 via-orange-500/5 to-transparent pointer-events-none rounded-2xl" />

      {/* Top Tagline */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-400" />
          <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wide">
            Sarkari Result Oracle & Application Dispatcher
          </h2>
        </div>
        <span className="text-xs text-slate-400">
          Universal DOM Sensing • 0% Hardcoded
        </span>
      </div>

      {/* Query Bar */}
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
            placeholder="Type exam wish ('apply for railway', 'bpsc teacher', 'ssc cgl') or paste any portal URL..."
            className="w-full pl-10 pr-4 py-3 rounded-xl bg-slate-950 border border-slate-700/80 focus:border-amber-500 focus:ring-1 focus:ring-amber-500/50 text-slate-100 placeholder-slate-500 text-sm font-medium outline-none transition-all disabled:opacity-50"
          />
        </div>

        <button
          type="submit"
          disabled={agentRunning || !query.trim()}
          className="px-6 py-3 rounded-xl bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:from-amber-400 hover:to-orange-500 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg shadow-amber-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
        >
          <Play className="w-4 h-4 fill-current" />
          <span>{agentRunning ? 'Bhaiya Driving...' : 'Bhaiya, Shuru Karo!'}</span>
        </button>
      </form>

      {/* Quick Launch Shortcuts */}
      <div className="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-slate-800/80">
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
          Quick Portals:
        </span>
        {quickPills.map((p, i) => (
          <button
            key={i}
            type="button"
            disabled={agentRunning}
            onClick={() => {
              setQuery(p.val);
            }}
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

      {/* Pre-Flight Oracle Consensus Verification Card */}
      {oracleResult && (
        <div className="mt-4 p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3 animate-fadeIn">
          <div className="flex items-start gap-3">
            <div className={`p-2 rounded-lg mt-0.5 ${
              oracleResult.is_gov_domain ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'
            }`}>
              {oracleResult.is_gov_domain ? (
                <ShieldCheck className="w-5 h-5" />
              ) : (
                <ShieldAlert className="w-5 h-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-200">
                  {oracleResult.official_name}
                </span>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                  oracleResult.is_gov_domain ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-300'
                }`}>
                  {oracleResult.authority_type}
                </span>
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/50 px-1.5 py-0.5 rounded border border-emerald-500/30">
                  Trust: {oracleResult.domain_trust_score}%
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 flex items-center gap-1 font-mono break-all">
                <span>{oracleResult.target_url}</span>
              </p>
              <p className="text-xs text-amber-300/90 mt-1 italic">
                💬 Bhaiya: "{oracleResult.hindi_advisory}"
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
              <span>Inspect Link</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
