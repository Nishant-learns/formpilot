import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ExternalLink,
  Download,
  Search,
  RefreshCw,
  ChevronRight,
  FileText,
  Lock,
  Layers,
  Check,
  X,
} from 'lucide-react';

export default function AuditLedgerPage({ notify, onSelectRun }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedChainRunId, setSelectedChainRunId] = useState(null);
  const [chainData, setChainData] = useState(null);
  const [verifyingChain, setVerifyingChain] = useState(false);

  useEffect(() => {
    fetchRuns();
  }, []);

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/runs?limit=50');
      if (res.ok) {
        const data = await res.json();
        setRuns(data.runs || []);
      }
    } catch (err) {
      console.error('Error fetching runs:', err);
      if (notify) notify('Failed to fetch run history.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyChain = async (runId) => {
    setSelectedChainRunId(runId);
    setVerifyingChain(true);
    setChainData(null);
    try {
      const res = await fetch(`/api/runs/${runId}/audit-chain`);
      if (res.ok) {
        const data = await res.json();
        setChainData(data);
        if (data.verified) {
          if (notify) notify(`Run ${runId} cryptographic SHA-256 Merkle chain verified intact.`, 'success');
        } else {
          if (notify) notify(`Run ${runId} failed cryptographic chain verification!`, 'error');
        }
      } else {
        if (notify) notify('Could not load audit chain for this run.', 'error');
      }
    } catch (err) {
      console.error('Error verifying chain:', err);
      if (notify) notify('Network error while verifying audit chain.', 'error');
    } finally {
      setVerifyingChain(false);
    }
  };

  const handleDownloadAudit = (runId) => {
    window.open(`/api/runs/${runId}/audit`, '_blank');
  };

  const filteredRuns = runs.filter((r) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (r.run_id && r.run_id.toLowerCase().includes(q)) ||
      (r.query && r.query.toLowerCase().includes(q)) ||
      (r.target_url && r.target_url.toLowerCase().includes(q)) ||
      (r.state && r.state.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      {/* Header Bar */}
      <div className="px-6 py-5 border-b border-white/[0.08] bg-slate-950/40 backdrop-blur-md shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1">
              <span>Workstation</span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-violet-400 font-semibold">Merkle Audit Ledger</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-white tracking-tight">Cryptographic Merkle Audit Ledger</h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-violet-500/10 text-violet-300 border border-violet-500/30">
                <Zap className="w-3 h-3" />
                SHA-256 Non-Repudiation
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={fetchRuns}
              className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh Ledger</span>
            </button>
          </div>
        </div>

        {/* Ledger Overview Cards */}
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Total Historical Runs</span>
            <span className="text-white font-bold font-mono text-base">{runs.length}</span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Integrity Standard</span>
            <span className="text-emerald-400 font-mono font-bold flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              Merkle SHA-256
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Safety Boundaries</span>
            <span className="text-slate-300 font-mono font-bold">Zero Final Submit</span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Ledger Storage</span>
            <span className="text-indigo-300 font-mono font-bold">Local Atomic Append</span>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-6xl w-full mx-auto space-y-6">
        {/* Search & Filter Bar */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filter by Run ID, Target Portal URL, or Status..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-xs text-white placeholder:text-slate-500 outline-none focus:border-indigo-400 font-mono"
            />
          </div>
        </div>

        {/* Runs Table */}
        <div className="glass-panel rounded-3xl border border-white/[0.08] overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/[0.02] border-b border-white/[0.08] text-[10px] uppercase font-mono text-slate-400">
                <tr>
                  <th className="px-5 py-3.5 font-bold">Run ID</th>
                  <th className="px-4 py-3.5 font-bold">Target Portal / Query</th>
                  <th className="px-4 py-3.5 font-bold">Mode</th>
                  <th className="px-4 py-3.5 font-bold">Status</th>
                  <th className="px-4 py-3.5 font-bold">Steps</th>
                  <th className="px-4 py-3.5 font-bold">Recorded At</th>
                  <th className="px-5 py-3.5 font-bold text-right">Cryptographic Audit</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {filteredRuns.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-slate-500 font-mono">
                      {loading ? 'Scanning run journals...' : 'No historical runs found matching criteria.'}
                    </td>
                  </tr>
                ) : (
                  filteredRuns.map((r) => {
                    const isSuccess = ['COMPLETED', 'AWAITING_PAYMENT', 'DONE'].includes(r.state);
                    const isFailed = r.state === 'FAILED';
                    return (
                      <tr key={r.run_id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="px-5 py-3.5 font-mono font-bold text-white whitespace-nowrap">
                          {r.run_id}
                        </td>
                        <td className="px-4 py-3.5 max-w-[240px] truncate text-slate-300">
                          {r.target_url || r.query || 'Direct Session'}
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.04] text-slate-300 border border-white/[0.06] uppercase">
                            {r.run_mode || 'fill'}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <span
                            className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold border ${
                              isSuccess
                                ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                                : isFailed
                                ? 'bg-red-500/15 text-red-400 border-red-500/30'
                                : 'bg-slate-500/15 text-slate-300 border-slate-500/30'
                            }`}
                          >
                            {r.state}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-slate-400 whitespace-nowrap">
                          {r.steps || 0} steps
                        </td>
                        <td className="px-4 py-3.5 font-mono text-slate-400 whitespace-nowrap text-[11px]">
                          {r.started_at ? new Date(r.started_at).toLocaleString() : 'N/A'}
                        </td>
                        <td className="px-5 py-3.5 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => handleVerifyChain(r.run_id)}
                              className="px-2.5 py-1.5 rounded-xl bg-violet-500/10 hover:bg-violet-500/20 text-violet-300 border border-violet-500/30 font-semibold text-[11px] flex items-center gap-1 transition-colors"
                              title="Verify Merkle Hash Chain"
                            >
                              <Zap className="w-3.5 h-3.5" />
                              <span>Verify Chain</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDownloadAudit(r.run_id)}
                              className="p-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 border border-white/[0.08] transition-colors"
                              title="Download Audit JSON Certificate"
                            >
                              <Download className="w-3.5 h-3.5" />
                            </button>
                            <a
                              href={`/runs/${r.run_id}`}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 border border-white/[0.08] transition-colors"
                              title="View Human Report"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Merkle Chain Inspector Modal / Overlay */}
      {selectedChainRunId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
          <div className="glass-panel-elevated max-w-4xl w-full max-h-[85vh] rounded-3xl border border-white/[0.12] flex flex-col shadow-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-white/[0.08] flex items-center justify-between shrink-0 bg-white/[0.02]">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-violet-500/15 border border-violet-500/30 flex items-center justify-center text-violet-300">
                  <Zap className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Cryptographic Chain Verification</h3>
                  <p className="text-[11px] font-mono text-slate-400">Run ID: {selectedChainRunId}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedChainRunId(null)}
                className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {verifyingChain ? (
                <div className="py-16 text-center">
                  <div className="w-8 h-8 rounded-full border-2 border-violet-400 border-t-transparent animate-spin mx-auto mb-3" />
                  <p className="text-xs font-mono text-slate-400">Validating Merkle block signatures & SHA-256 sequence...</p>
                </div>
              ) : chainData ? (
                <div className="space-y-4">
                  {/* Verification Banner */}
                  <div
                    className={`p-4 rounded-2xl border flex items-center justify-between gap-3 text-xs ${
                      chainData.verified
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                        : 'bg-red-500/10 border-red-500/30 text-red-300'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      {chainData.verified ? <Check className="w-5 h-5 text-emerald-400" /> : <AlertTriangle className="w-5 h-5 text-red-400" />}
                      <div>
                        <span className="font-bold block">
                          {chainData.verified ? 'Merkle Chain Cryptographically Verified' : 'Integrity Verification Failed'}
                        </span>
                        <span className="text-[11px] font-mono opacity-80">
                          {chainData.verified
                            ? `All ${chainData.total_entries} blocks verified without tampering.`
                            : chainData.verification_error}
                        </span>
                      </div>
                    </div>
                    {chainData.head_hash && (
                      <div className="text-right font-mono text-[10px]">
                        <span className="text-slate-400 block">Head Block Hash</span>
                        <span className="text-white font-bold">{chainData.head_hash.slice(0, 16)}…</span>
                      </div>
                    )}
                  </div>

                  {/* Block by Block Sequence */}
                  <div className="space-y-2.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider font-mono text-slate-400">
                      Sequential Block Ledger
                    </span>
                    {(chainData.chain || []).map((b) => (
                      <div key={b.index} className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/[0.06] text-xs font-mono space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-indigo-300 font-bold">
                            Block #{b.index}: {b.event_type}
                          </span>
                          <span className="text-[10px] text-slate-400">{b.timestamp}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 border-t border-white/[0.04]">
                          <div>
                            <span className="text-slate-500 block">Prev Hash:</span>
                            <span className="text-slate-300 truncate block">{b.prev_hash}</span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Block Hash:</span>
                            <span className="text-violet-300 truncate block">{b.entry_hash}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
