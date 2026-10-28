import React, { useState, useEffect } from 'react';
import {
  X,
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
} from 'lucide-react';

const DEFAULTS = {
  mode: 'auto',
  headless: true,
  tinyfish_api_key: '',
  proxy_region: 'in',
  timeout_seconds: 90,
  ntfy_topic: 'formpilot-demo-otp',
};

export default function TinyFishSettingsModal(props) {
  if (!props.isOpen) return null;
  return <SettingsContent {...props} />;
}

function SettingsContent({ onClose, onConfigSaved }) {
  const [config, setConfig] = useState(DEFAULTS);
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [wallet, setWallet] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    fetchConfig();
    fetchWallet();
  }, []);

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
      setLoadError('Could not load settings. You can still try the connection test.');
    }
  };

  const fetchWallet = async () => {
    try {
      const res = await fetch('/api/engine/wallet');
      if (res.ok) setWallet(await res.json());
    } catch (err) {
      // Wallet display is optional.
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/engine/test-tinyfish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: config.tinyfish_api_key || '***' }),
      });
      const data = await res.json();
      setTestResult(data);
      if (data.success) fetchWallet();
    } catch (err) {
      setTestResult({
        success: false,
        message: 'Could not reach the connection test. Check your network and try again.',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        mode: config.mode,
        headless: Boolean(config.headless),
        tinyfish_api_key: config.tinyfish_api_key || '***',
        proxy_region: config.proxy_region,
        timeout_seconds: Number(config.timeout_seconds) || DEFAULTS.timeout_seconds,
        ntfy_topic: config.ntfy_topic || DEFAULTS.ntfy_topic,
      };
      const res = await fetch('/api/engine/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Save failed');
      const data = await res.json();
      if (onConfigSaved) onConfigSaved(data.config);
      onClose();
    } catch (err) {
      setTestResult({
        success: false,
        message: 'Could not save the settings. Please try again.',
      });
    } finally {
      setSaving(false);
    }
  };

  const modes = [
    {
      id: 'auto',
      title: 'Automatic',
      icon: Sparkles,
      color: 'text-amber-400',
      description: 'Use TinyFish cloud when a key is available, otherwise use this device. This is the recommended default.',
    },
    {
      id: 'local',
      title: 'This device',
      icon: Server,
      color: 'text-emerald-400',
      description: 'Run the browser locally. Page data stays on this device, and no cloud session is created.',
    },
    {
      id: 'cloud',
      title: 'TinyFish cloud',
      icon: Cloud,
      color: 'text-cyan-400',
      description: 'Run the browser on TinyFish infrastructure. Useful for slow portals or networks with regional restrictions.',
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-2xl w-full shadow-2xl overflow-hidden flex flex-col">
        <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Cloud className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-white">Connection settings</h2>
              <p className="text-xs text-slate-400">
                Choose where the browser runs and manage the TinyFish connection.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200"
            title="Close settings"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto max-h-[75vh]">
          {loadError && (
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300">
              {loadError}
            </div>
          )}

          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
              Browser mode
            </label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {modes.map((mode) => {
                const Icon = mode.icon;
                const selected = config.mode === mode.id;
                return (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => setConfig({ ...config, mode: mode.id })}
                    className={`p-4 rounded-2xl border-2 text-left transition-all ${
                      selected
                        ? 'bg-cyan-500/10 border-cyan-500/80 shadow-md shadow-cyan-500/10'
                        : 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Icon className={`w-4 h-4 ${selected ? mode.color : 'text-slate-400'}`} />
                        <span className="text-sm font-bold text-white">{mode.title}</span>
                      </div>
                      {selected && <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />}
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">{mode.description}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5" />
                <span>TinyFish connection</span>
              </span>
              <a
                href="https://tinyfish.ai"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1"
              >
                <span>Get an API key</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-400 font-semibold block mb-1">API key</label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={config.tinyfish_api_key || ''}
                    onChange={(e) => setConfig({ ...config, tinyfish_api_key: e.target.value })}
                    placeholder={keyConfigured ? 'A key is already saved. Leave blank to keep it.' : 'Paste your TinyFish API key'}
                    className="w-full pl-3 pr-20 py-2.5 rounded-xl bg-slate-900 border border-slate-700 focus:border-cyan-500 text-white font-mono outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-2 px-2 py-1 text-[10px] font-semibold text-slate-400 hover:text-slate-200 bg-slate-800 rounded border border-slate-700"
                  >
                    {showKey ? 'Hide' : 'Show'}
                  </button>
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {keyConfigured
                    ? 'A key is saved on this device. It is never shown in the browser after saving.'
                    : 'The key is stored on this device and is never included in status messages.'}
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Browser region</label>
                  <select
                    value={config.proxy_region || 'in'}
                    onChange={(e) => setConfig({ ...config, proxy_region: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white font-medium"
                  >
                    <option value="in">India</option>
                    <option value="us">United States</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Timeout (seconds)</label>
                  <input
                    type="number"
                    min={30}
                    max={300}
                    value={config.timeout_seconds || DEFAULTS.timeout_seconds}
                    onChange={(e) => setConfig({ ...config, timeout_seconds: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Alert topic</label>
                  <input
                    type="text"
                    value={config.ntfy_topic || ''}
                    onChange={(e) => setConfig({ ...config, ntfy_topic: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-slate-300 font-mono text-[11px]"
                  />
                </div>
              </div>

              <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={testing}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 font-semibold text-xs border border-cyan-500/30 flex items-center gap-1.5 transition-all"
                >
                  <Activity className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
                  <span>{testing ? 'Testing…' : 'Test connection'}</span>
                </button>

                {testResult && (
                  <div
                    className={`text-xs font-semibold px-3 py-1.5 rounded-lg border flex flex-col items-start gap-1 ${
                      testResult.success
                        ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                        : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      {testResult.success ? (
                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                      ) : (
                        <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                      )}
                      <span>{testResult.message}</span>
                    </div>
                    {!testResult.success && (
                      <div className="flex flex-wrap items-center gap-2 pl-5 font-mono text-[10px] text-slate-400">
                        {testResult.status && (
                          <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-amber-200">
                            {testResult.status}
                          </span>
                        )}
                        {testResult.status_code && <span>HTTP {testResult.status_code}</span>}
                        {testResult.retry_after != null && (
                          <span>Retry in {testResult.retry_after}s</span>
                        )}
                        {testResult.rate_limit?.remaining != null && (
                          <span>
                            {testResult.rate_limit.remaining}
                            {testResult.rate_limit.limit != null ? `/${testResult.rate_limit.limit}` : ''} left
                            this minute
                          </span>
                        )}
                        {['INSUFFICIENT_CREDITS', 'FREE_ALLOWANCE_EXHAUSTED', 'FORBIDDEN'].includes(
                          testResult.status,
                        ) && (
                          <a
                            href="https://agent.tinyfish.ai/wallet"
                            target="_blank"
                            rel="noreferrer"
                            className="underline text-amber-200"
                          >
                            Open wallet
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {wallet?.available_balance != null && (
                <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                  <Wallet
                    className={`w-3.5 h-3.5 ${
                      Number(wallet.available_balance) > 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}
                  />
                  <span>
                    TinyFish balance: {wallet.available_balance} {wallet.currency || 'USD'}
                  </span>
                  {Number(wallet.available_balance) <= 0 && (
                    <a
                      href="https://agent.tinyfish.ai/wallet"
                      target="_blank"
                      rel="noreferrer"
                      className="text-amber-300 underline font-semibold"
                    >
                      Top up to resume cloud runs
                    </a>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs text-amber-200/90 space-y-1">
            <span className="font-bold flex items-center gap-1 text-amber-300">
              <ShieldCheck className="w-4 h-4" />
              <span>If the cloud browser cannot start</span>
            </span>
            <p className="leading-relaxed">
              FormPilot will use this device's browser and show that clearly in the activity log.
              It will never pretend a cloud session is running when it isn't.
            </p>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            <Globe2 className="w-3.5 h-3.5" />
            <span>Search results and portal checks use TinyFish Search. Cloud browser sessions are optional.</span>
          </div>
        </div>

        <div className="px-6 py-4 bg-slate-950 border-t border-slate-800 flex justify-end gap-3 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-slate-950 text-xs font-extrabold shadow-lg shadow-cyan-500/20 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
