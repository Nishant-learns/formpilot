import React, { useState, useEffect } from 'react';
import {
  Cloud,
  Server,
  Key,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Activity,
  ExternalLink,
  Wallet,
  Globe2,
  Sparkles,
  Zap,
  Lock,
  RefreshCw,
  Save,
  Check,
  Sliders,
  ChevronRight,
  Cpu,
} from 'lucide-react';

const DEFAULTS = {
  mode: 'auto',
  headless: true,
  tinyfish_api_key: '',
  proxy_region: 'in',
  timeout_seconds: 90,
  ntfy_topic: 'formpilot-demo-otp',
};

export default function SettingsPage({ onConfigSaved, notify }) {
  const [config, setConfig] = useState(DEFAULTS);
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [wallet, setWallet] = useState(null);
  const [activeTab, setActiveTab] = useState('engine');
  const [circuitBreakers, setCircuitBreakers] = useState({});
  const [deepHealth, setDeepHealth] = useState(null);
  const [llm, setLlm] = useState({
    model: '',
    base_url: '',
    api_key: '',
    configured: false,
    local: false,
  });
  const [llmShowKey, setLlmShowKey] = useState(false);

  useEffect(() => {
    fetchConfig();
    fetchWallet();
    fetchLlmConfig();
    fetchSystemTelemetry();
  }, []);

  const fetchSystemTelemetry = async () => {
    try {
      const [cbRes, healthRes] = await Promise.all([
        fetch('/api/system/circuit-breakers'),
        fetch('/api/system/health/deep'),
      ]);
      if (cbRes.ok) {
        const cbData = await cbRes.json();
        setCircuitBreakers(cbData.breakers || {});
      }
      if (healthRes.ok) {
        const healthData = await healthRes.json();
        setDeepHealth(healthData);
      }
    } catch (err) {
      console.error('Error fetching telemetry:', err);
    }
  };

  const fetchLlmConfig = async () => {
    try {
      const res = await fetch('/api/chat/config');
      if (!res.ok) return;
      const data = await res.json();
      setLlm({
        model: data.model || '',
        base_url: data.base_url || '',
        api_key: '',
        configured: Boolean(data.configured),
        local: Boolean(data.local),
      });
    } catch (err) {
      // Optional
    }
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/engine/config');
      if (!res.ok) throw new Error('Could not load settings');
      const data = await res.json();
      setConfig({
        ...DEFAULTS,
        ...data,
        tinyfish_api_key: data.tinyfish_api_key === '***' ? '' : data.tinyfish_api_key || '',
      });
      setKeyConfigured(Boolean(data.tinyfish_key_configured));
    } catch (err) {
      if (notify) notify('Could not load settings from server.', 'error');
    }
  };

  const fetchWallet = async () => {
    try {
      const res = await fetch('/api/engine/wallet');
      if (res.ok) setWallet(await res.json());
    } catch (err) {
      // Optional
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/engine/test-tinyfish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: config.tinyfish_api_key || undefined,
          proxy_region: config.proxy_region,
        }),
      });
      const data = await res.json();
      setTestResult(data);
      if (data.success && notify) {
        notify('TinyFish microVM connection verified!', 'success');
      }
    } catch (err) {
      setTestResult({ success: false, error: 'Network error contacting test endpoint.' });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/engine/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: config.mode,
          headless: config.headless,
          proxy_region: config.proxy_region,
          timeout_seconds: config.timeout_seconds,
          ntfy_topic: config.ntfy_topic,
          ...(config.tinyfish_api_key ? { tinyfish_api_key: config.tinyfish_api_key } : {}),
        }),
      });
      if (res.ok) {
        const saved = await res.json();
        setKeyConfigured(Boolean(saved.tinyfish_key_configured));
        if (onConfigSaved) onConfigSaved(saved);
        setSaveSuccess(true);
        if (notify) notify('Engine & distributed settings committed.', 'success');
        setTimeout(() => setSaveSuccess(false), 2400);
      } else {
        if (notify) notify('Failed to save settings.', 'error');
      }
    } catch (err) {
      if (notify) notify('Error saving configuration.', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      {/* Header Bar */}
      <div className="px-6 py-5 border-b border-white/[0.08] bg-slate-950/40 backdrop-blur-md shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1">
              <span>Workstation</span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-indigo-400 font-semibold">Engine & Settings</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-white tracking-tight">Engine & Distributed Settings</h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
                <Sliders className="w-3 h-3" />
                Hyper-Scale Architecture
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={fetchSystemTelemetry}
              className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
              <span>Refresh Telemetry</span>
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all shadow-sm ${
                saveSuccess
                  ? 'bg-emerald-600 text-white border border-emerald-500'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-400/40 shadow-indigo-500/20'
              }`}
            >
              {saveSuccess ? (
                <>
                  <Check className="w-4 h-4" />
                  <span>Settings Committed!</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>{saving ? 'Saving...' : 'Commit Settings'}</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* System Health Ribbon */}
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Execution Engine</span>
            <span className="text-white font-bold font-mono">
              {config.mode === 'cloud' ? 'TinyFish MicroVM' : 'Local Playwright'}
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">SSRF Guard Status</span>
            <span className="text-emerald-400 font-mono font-bold flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              Active (Protected)
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Circuit Breakers</span>
            <span className="text-indigo-300 font-mono font-bold">
              {Object.keys(circuitBreakers).length || 1} Registered
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Memory RSS</span>
            <span className="text-slate-300 font-mono font-bold">
              {deepHealth?.resources?.memory_rss_mb ? `${deepHealth.resources.memory_rss_mb} MB` : 'Normal'}
            </span>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-6xl w-full mx-auto space-y-6">
        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-white/[0.08] pb-1 overflow-x-auto">
          {[
            { id: 'engine', label: '1. Browser Automation Engine', icon: <Server className="w-4 h-4" /> },
            { id: 'resilience', label: '2. Resilience & Circuit Breakers', icon: <Zap className="w-4 h-4" /> },
            { id: 'security', label: '3. Cybersecurity & SSRF Defense', icon: <ShieldCheck className="w-4 h-4" /> },
            { id: 'assistant', label: '4. AI Copilot Model', icon: <Sparkles className="w-4 h-4" /> },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 rounded-xl text-xs font-semibold flex items-center gap-2 transition-all whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-indigo-500/20 text-indigo-200 border border-indigo-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04] border border-transparent'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* TAB 1: ENGINE */}
        {activeTab === 'engine' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="border-b border-white/[0.06] pb-3">
              <h3 className="text-sm font-bold text-white">Browser Fleet & Proxy Configuration</h3>
              <p className="text-xs text-slate-400">Control whether form filling runs on local headless Chromium or an ephemeral cloud microVM pool.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs">
              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Execution Environment</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setConfig({ ...config, mode: 'local' })}
                    className={`p-3.5 rounded-2xl border text-left transition-all ${
                      config.mode === 'local'
                        ? 'bg-indigo-500/20 border-indigo-400 text-white shadow-sm'
                        : 'bg-white/[0.02] border-white/[0.06] text-slate-400 hover:bg-white/[0.04]'
                    }`}
                  >
                    <span className="font-bold block text-xs">Local Chromium</span>
                    <span className="text-[10px] text-slate-400">Zero cloud latency</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setConfig({ ...config, mode: 'cloud' })}
                    className={`p-3.5 rounded-2xl border text-left transition-all ${
                      config.mode === 'cloud'
                        ? 'bg-indigo-500/20 border-indigo-400 text-white shadow-sm'
                        : 'bg-white/[0.02] border-white/[0.06] text-slate-400 hover:bg-white/[0.04]'
                    }`}
                  >
                    <span className="font-bold block text-xs">TinyFish Cloud</span>
                    <span className="text-[10px] text-slate-400">Isolated microVM</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Proxy Gateway Region</label>
                <select
                  value={config.proxy_region}
                  onChange={(e) => setConfig({ ...config, proxy_region: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 outline-none"
                >
                  <option value="in">India (Residential IN / Mumbai / Delhi)</option>
                  <option value="direct">Direct Outbound (No Proxy)</option>
                </select>
              </div>

              <div className="md:col-span-2">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-slate-300 font-semibold">TinyFish API Key</label>
                  {keyConfigured && (
                    <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-1">
                      <Check className="w-3 h-3" /> Configured in Environment
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={config.tinyfish_api_key}
                    onChange={(e) => setConfig({ ...config, tinyfish_api_key: e.target.value })}
                    placeholder={keyConfigured ? '••••••••••••••••••••••••' : 'Enter TinyFish API token'}
                    className="flex-1 px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono text-xs focus:border-indigo-400 outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="px-3 py-2.5 rounded-xl bg-white/[0.04] text-slate-300 text-xs border border-white/[0.08]"
                  >
                    {showKey ? 'Hide' : 'Show'}
                  </button>
                  <button
                    type="button"
                    onClick={handleTestConnection}
                    disabled={testing}
                    className="px-4 py-2.5 rounded-xl bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold text-xs hover:bg-indigo-500/30 transition-colors"
                  >
                    {testing ? 'Testing...' : 'Test Connection'}
                  </button>
                </div>
                {testResult && (
                  <div
                    className={`mt-2 p-3 rounded-xl border text-xs font-mono ${
                      testResult.success
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                        : 'bg-red-500/10 border-red-500/30 text-red-300'
                    }`}
                  >
                    {testResult.success
                      ? '✓ Connection verified with microVM gateway.'
                      : `✗ Test failed: ${testResult.error}`}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: RESILIENCE & CIRCUIT BREAKERS */}
        {activeTab === 'resilience' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="border-b border-white/[0.06] pb-3">
              <h3 className="text-sm font-bold text-white">Circuit Breaker Telemetry & Fail-Fast Protection</h3>
              <p className="text-xs text-slate-400">Protects FormPilot against 502/503/504 Bad Gateway storms during government recruitment portal traffic spikes.</p>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] space-y-1">
                  <span className="text-[10px] font-mono text-slate-400 uppercase">State Machine</span>
                  <span className="font-bold text-emerald-400 text-sm block">CLOSED (Normal)</span>
                  <p className="text-slate-500 text-[11px]">Requests pass unobstructed</p>
                </div>
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] space-y-1">
                  <span className="text-[10px] font-mono text-slate-400 uppercase">Trip Threshold</span>
                  <span className="font-bold text-white text-sm block">5 Consecutive Failures</span>
                  <p className="text-slate-500 text-[11px]">Automatically trips to OPEN</p>
                </div>
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] space-y-1">
                  <span className="text-[10px] font-mono text-slate-400 uppercase">Recovery Backoff</span>
                  <span className="font-bold text-indigo-300 text-sm block">30 Seconds Cooldown</span>
                  <p className="text-slate-500 text-[11px]">Transitions to HALF_OPEN canary</p>
                </div>
              </div>

              {/* Breakers Table */}
              <div className="p-4 rounded-2xl bg-slate-950/80 border border-white/[0.08] overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="text-[10px] font-mono uppercase text-slate-400 border-b border-white/[0.08]">
                    <tr>
                      <th className="pb-2 font-bold">Breaker Name</th>
                      <th className="pb-2 font-bold">Status</th>
                      <th className="pb-2 font-bold">Failures</th>
                      <th className="pb-2 font-bold">Total Trips</th>
                      <th className="pb-2 font-bold">Health</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04] font-mono">
                    {Object.entries(circuitBreakers).length === 0 ? (
                      <tr>
                        <td className="py-3 text-white">gov-portal-default</td>
                        <td className="py-3 text-emerald-400">CLOSED</td>
                        <td className="py-3 text-slate-400">0 / 5</td>
                        <td className="py-3 text-slate-400">0</td>
                        <td className="py-3 text-emerald-400 font-bold">Healthy ✓</td>
                      </tr>
                    ) : (
                      Object.entries(circuitBreakers).map(([name, b]) => (
                        <tr key={name}>
                          <td className="py-3 text-white font-bold">{name}</td>
                          <td className="py-3 text-emerald-400">{b.state}</td>
                          <td className="py-3 text-slate-400">{b.failure_count} / {b.failure_threshold}</td>
                          <td className="py-3 text-slate-400">{b.total_trips}</td>
                          <td className="py-3 text-emerald-400 font-bold">{b.healthy ? 'Healthy ✓' : 'Degraded !'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: CYBERSECURITY & SSRF */}
        {activeTab === 'security' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="border-b border-white/[0.06] pb-3">
              <h3 className="text-sm font-bold text-white">Active Defense: SSRF Guard & Privacy Scrubbing</h3>
              <p className="text-xs text-slate-400">Multi-layer boundary defenses preventing cloud credential theft and PII leakages.</p>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">Cloud Metadata Protection (IMDS)</span>
                  <span className="text-[11px] text-slate-400">Strictly blocks 169.254.169.254, fd00:ec2::254, and internal metadata APIs</span>
                </div>
                <span className="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  ENFORCED
                </span>
              </div>

              <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">RFC 1918 Private Subnet Shield</span>
                  <span className="text-[11px] text-slate-400">Disallows navigation to 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16</span>
                </div>
                <span className="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  ENFORCED
                </span>
              </div>

              <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">DNS Rebinding & NAT64 Inspection</span>
                  <span className="text-[11px] text-slate-400">Resolves hostnames to TCP addresses prior to dispatch; inspects 64:ff9b::/96</span>
                </div>
                <span className="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  ENFORCED
                </span>
              </div>

              <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                <div>
                  <span className="font-bold text-white block">Zero PII Leakage Scrubbing</span>
                  <span className="text-[11px] text-slate-400">Masks Aadhaar, PAN, phone numbers, and bearer credentials from error logs and third-party prompts</span>
                </div>
                <span className="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  ENFORCED
                </span>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: AI ASSISTANT LLM */}
        {activeTab === 'assistant' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="border-b border-white/[0.06] pb-3">
              <h3 className="text-sm font-bold text-white">AI Copilot Reasoning Engine</h3>
              <p className="text-xs text-slate-400">Configures the natural language copilot model answering queries and resolving form fields.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs">
              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Model Name</label>
                <input
                  type="text"
                  value={llm.model || 'gpt-4o-mini'}
                  onChange={(e) => setLlm({ ...llm, model: e.target.value })}
                  placeholder="gpt-4o-mini"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Base URL (OpenAI / Ollama / Local)</label>
                <input
                  type="text"
                  value={llm.base_url || 'https://api.openai.com/v1'}
                  onChange={(e) => setLlm({ ...llm, base_url: e.target.value })}
                  placeholder="https://api.openai.com/v1"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
