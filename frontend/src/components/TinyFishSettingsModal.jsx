import React, { useState, useEffect } from 'react';
import { X, Cloud, Server, Key, Globe2, ShieldCheck, CheckCircle2, AlertTriangle, Activity, ArrowRight, ExternalLink } from 'lucide-react';

export default function TinyFishSettingsModal({ isOpen, onClose, onConfigSaved }) {
  if (!isOpen) return null;

  const [config, setConfig] = useState({
    mode: 'local',
    headless: true,
    tinyfish_api_key: '',
    tinyfish_endpoint: 'https://api.tinyfish.ai/v1',
    tinyfish_cdp_url: 'wss://connect.tinyfish.ai/cdp',
    proxy_region: 'in',
    stealth_mode: true
  });

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/engine/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (err) {
      console.error('Error fetching engine config:', err);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch('/api/engine/test-tinyfish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: config.tinyfish_api_key })
      });
      const data = await res.json();
      setTestResult(data);
    } catch (err) {
      setTestResult({
        success: false,
        message: 'Network error communicating with TinyFish test service.'
      });
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
        body: JSON.stringify(config)
      });
      if (res.ok) {
        const data = await res.json();
        if (onConfigSaved) onConfigSaved(data.config);
        onClose();
      }
    } catch (err) {
      console.error('Error saving engine config:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-2xl w-full shadow-2xl overflow-hidden flex flex-col">
        
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Cloud className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-white flex items-center gap-2">
                <span>Engine Architecture & TinyFish Cloud Browser</span>
              </h2>
              <p className="text-xs text-slate-400">
                Configure browser execution, residential proxy routing, and cloud agent infrastructure
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5 overflow-y-auto max-h-[75vh]">
          
          {/* Engine Mode Selection */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
              Execution Runtime Engine
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              
              {/* Option 1: Local Autonomous Playwright */}
              <div
                onClick={() => setConfig({ ...config, mode: 'local' })}
                className={`p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                  config.mode === 'local'
                    ? 'bg-emerald-500/10 border-emerald-500/80 shadow-md shadow-emerald-500/10'
                    : 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Server className={`w-4 h-4 ${config.mode === 'local' ? 'text-emerald-400' : 'text-slate-400'}`} />
                    <span className="text-sm font-bold text-white">Local Playwright</span>
                  </div>
                  {config.mode === 'local' && (
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                  )}
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Direct Chromium browser running natively on your local machine. Zero cloud dependency, instant execution, 100% private.
                </p>
              </div>

              {/* Option 2: TinyFish Cloud Browser */}
              <div
                onClick={() => setConfig({ ...config, mode: 'tinyfish' })}
                className={`p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                  config.mode === 'tinyfish'
                    ? 'bg-cyan-500/10 border-cyan-500/80 shadow-md shadow-cyan-500/10'
                    : 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Cloud className={`w-4 h-4 ${config.mode === 'tinyfish' ? 'text-cyan-400' : 'text-slate-400'}`} />
                    <span className="text-sm font-bold text-white">TinyFish Cloud Agent</span>
                  </div>
                  {config.mode === 'tinyfish' && (
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
                  )}
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Cloud managed browser infrastructure with rotating residential IP proxy for hostile state portals, geo-blocks, and anti-bot bypass.
                </p>
              </div>

            </div>
          </div>

          {/* TinyFish Cloud Credentials & Proxy Settings */}
          <div className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5" />
                <span>TinyFish API Credentials & Proxy Lock</span>
              </span>
              <a
                href="https://tinyfish.ai"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1"
              >
                <span>Get API Key from tinyfish.ai</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-400 font-semibold block mb-1">TinyFish API Key</label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={config.tinyfish_api_key || ''}
                    onChange={(e) => setConfig({ ...config, tinyfish_api_key: e.target.value })}
                    placeholder="tf_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
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
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Residential Proxy Region</label>
                  <select
                    value={config.proxy_region}
                    onChange={(e) => setConfig({ ...config, proxy_region: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-white font-medium"
                  >
                    <option value="in">🇮🇳 India Residential Proxy (Delhi/Mumbai - Required for State PSCs)</option>
                    <option value="auto">🌐 Auto Geo-Routing</option>
                    <option value="us">🇺🇸 US Cloud Node</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Cloud CDP WebSocket URL</label>
                  <input
                    type="text"
                    value={config.tinyfish_cdp_url}
                    onChange={(e) => setConfig({ ...config, tinyfish_cdp_url: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-slate-300 font-mono text-[11px]"
                  />
                </div>
              </div>

              {/* Test Connection Button & Status */}
              <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={testing}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 font-semibold text-xs border border-cyan-500/30 flex items-center gap-1.5 transition-all"
                >
                  <Activity className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
                  <span>{testing ? 'Testing Ping...' : 'Test TinyFish Connection'}</span>
                </button>

                {testResult && (
                  <div className={`text-xs font-semibold px-3 py-1.5 rounded-lg border flex items-center gap-1.5 ${
                    testResult.success
                      ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                      : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                  }`}>
                    {testResult.success ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                    <span>{testResult.message}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Practical Workflows & Government Portals Info */}
          <div className="p-3.5 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs text-amber-200/90 space-y-1">
            <span className="font-bold flex items-center gap-1 text-amber-300">
              <ShieldCheck className="w-4 h-4" />
              <span>Production Invariant Note:</span>
            </span>
            <p className="leading-relaxed">
              If no TinyFish API key is provided or cloud proxy is unreachable, FormPilot automatically defaults to the Local Autonomous Playwright Engine. Both modes execute the exact same universal DOM sensing and human-in-the-loop security gates without compromise.
            </p>
          </div>

        </div>

        {/* Footer */}
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
            className="px-6 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-slate-950 text-xs font-extrabold shadow-lg shadow-cyan-500/20"
          >
            {saving ? 'Applying Settings...' : 'Save Configuration'}
          </button>
        </div>

      </div>
    </div>
  );
}
