import React, { useEffect, useRef, useState } from 'react';
import Header from './components/Header';
import PortalLauncher from './components/PortalLauncher';
import LiveViewport from './components/LiveViewport';
import CognitiveStream from './components/CognitiveStream';
import LiveChat from './components/LiveChat';
import HumanCheckpointModal from './components/HumanCheckpointModal';
import FormMapPanel from './components/FormMapPanel';
import OneVaultDrawer from './components/OneVaultDrawer';
import BiometricsStudio from './components/BiometricsStudio';
import TinyFishSettingsModal from './components/TinyFishSettingsModal';
import { MessageSquare, ScanSearch, Terminal } from 'lucide-react';

const ACTIVE_STATES = new Set(['RESOLVING', 'RUNNING', 'WAITING_FOR_USER', 'PAUSED']);

export default function App() {
  const [runState, setRunState] = useState('IDLE');
  const [runMode, setRunMode] = useState('fill');
  const [events, setEvents] = useState([]);
  const [screenshot, setScreenshot] = useState('');
  const [currentGate, setCurrentGate] = useState(null);
  const [gateHidden, setGateHidden] = useState(false);
  const [currentSection, setCurrentSection] = useState(1);
  const [liveSession, setLiveSession] = useState(null);
  const [formMap, setFormMap] = useState(null);
  const [recipe, setRecipe] = useState(null);
  const [rescanning, setRescanning] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [rightTab, setRightTab] = useState('chat'); // 'chat' | 'stream' | 'map'
  const [chatMessages, setChatMessages] = useState([]);

  // Engine config state
  const [engineConfig, setEngineConfig] = useState({
    mode: 'local',
    proxy_region: 'in',
    tinyfish_api_key: ''
  });

  // Drawers & Modals
  const [isVaultOpen, setIsVaultOpen] = useState(false);
  const [isBiometricsOpen, setIsBiometricsOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const wsRef = useRef(null);
  const gateKeyRef = useRef('');
  const reconnectRef = useRef(null);
  const currentGateRef = useRef(null);

  const agentRunning = ACTIVE_STATES.has(runState);
  const inspectOpen = runState === 'INSPECT_READY' && Boolean(liveSession);
  const busy = agentRunning || inspectOpen;

  // Initialize WebSocket connection, agent state and global key listeners
  useEffect(() => {
    currentGateRef.current = currentGate;
  }, [currentGate]);

  useEffect(() => {
    connectWebSocket();
    fetchEngineConfig();
    fetchAgentState();

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && currentGateRef.current) {
        setGateHidden(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchEngineConfig = async () => {
    try {
      const res = await fetch('/api/engine/config');
      if (res.ok) {
        const data = await res.json();
        setEngineConfig(data);
      }
    } catch (err) {
      console.error('Config fetch error:', err);
    }
  };

  const fetchAgentState = async () => {
    try {
      const res = await fetch('/api/agent/state');
      if (!res.ok) return;
      const data = await res.json();
      setRunState(data.state || 'IDLE');
      setRunMode(data.run_mode || 'fill');
      setLiveSession(data.live_session || null);
      setFormMap(data.form_map || null);
      setRecipe(data.recipe || null);
      setCurrentSection(data.current_section || 1);
      if (data.active_gate) {
        setCurrentGate(data.active_gate);
        setGateHidden(false);
        gateKeyRef.current = gateIdentity(data.active_gate);
      }
    } catch (err) {
      console.error('Agent state fetch error:', err);
    }
  };

  function gateIdentity(gate) {
    if (!gate) return '';
    return [
      gate.gate_type,
      gate.field_key || '',
      gate.section_number || '',
      gate.title || '',
    ].join(':');
  }

  const connectWebSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/cockpit`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Cockpit WS] Connected to FormPilot.');
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);

        // Add to cognitive events stream
        if (data.phase && data.message) {
          setEvents((prev) => [...prev.slice(-399), data]);
        }

        // Update live screenshot fallback
        if (data.screenshot) {
          setScreenshot(data.screenshot);
        }

        if (data.state) {
          setRunState(data.state);
        }
        if (data.run_mode) {
          setRunMode(data.run_mode);
        }
        if ('live_session' in data) {
          setLiveSession(data.live_session || null);
        }
        if (data.form_map) {
          setFormMap((previous) => (
            previous?.fingerprint === data.form_map.fingerprint && previous?.url === data.form_map.url
              ? previous
              : data.form_map
          ));
        }
        if ('recipe' in data) {
          setRecipe(data.recipe || null);
        }

        // Update active gate. A new checkpoint opens the panel; a hidden panel
        // stays hidden for the same gate.
        if ('active_gate' in data) {
          const nextGate = data.active_gate;
          setCurrentGate(nextGate);
          if (!nextGate) {
            gateKeyRef.current = '';
            setGateHidden(false);
          } else {
            const key = gateIdentity(nextGate);
            if (key !== gateKeyRef.current) {
              gateKeyRef.current = key;
              setGateHidden(false);
            }
          }
        }

        // Update current section
        if (data.current_section) {
          setCurrentSection(data.current_section);
        }

        // Handle a chat reply from FormPilot
        if (data.type === 'CHAT_MESSAGE') {
          setChatMessages((prev) => [
            ...prev,
            {
              sender: data.sender || 'FormPilot',
              text: data.message,
              time: data.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              action_taken: data.action_taken,
              field_updated: data.field_updated,
              new_value: data.new_value
            }
          ]);
        }
      } catch (err) {
        console.error('[Cockpit WS] Parse error:', err);
      }
    };

    ws.onclose = () => {
      console.log('[Cockpit WS] Disconnected. Reconnecting in 2s...');
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      reconnectRef.current = setTimeout(connectWebSocket, 2000);
    };
  };

  // Launch Agent
  const handleLaunch = async (queryOrUrl, mode = 'fill') => {
    setEvents([]);
    setCurrentGate(null);
    setGateHidden(false);
    gateKeyRef.current = '';
    setScreenshot('');
    setLiveSession(null);
    setFormMap(null);
    setRecipe(null);
    setRunMode(mode);
    setRunState('RESOLVING');
    try {
      const res = await fetch('/api/agent/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_or_url: queryOrUrl, mode })
      });
      const data = await res.json();
      if (!data.success) {
        alert(data.message || 'Could not start the application sequence.');
        setRunState('IDLE');
      }
    } catch (err) {
      console.error('Launch error:', err);
      setRunState('FAILED');
    }
  };

  // Emergency Stop Agent
  const handleStop = async () => {
    try {
      await fetch('/api/agent/stop', { method: 'POST' });
    } catch (err) {
      console.error('Stop error:', err);
    }
    setRunState('STOPPED');
    setCurrentGate(null);
    setGateHidden(false);
    gateKeyRef.current = '';
    setLiveSession(null);
    setScreenshot('');
    setFormMap(null);
    setRecipe(null);
  };

  // Submit Candidate Gate Response
  const handleSubmitUserResponse = async (payload) => {
    try {
      setCurrentGate(null);
      setGateHidden(false);
      gateKeyRef.current = '';
      await fetch('/api/agent/user-response', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (err) {
      console.error('User response submission error:', err);
    }
  };

  const handleDismissGate = async () => {
    setCurrentGate(null);
    setGateHidden(false);
    gateKeyRef.current = '';
    try {
      await fetch('/api/agent/dismiss-gate', { method: 'POST' });
    } catch (err) {
      console.error('Dismiss gate error:', err);
    }
  };

  const handleRescan = async () => {
    setRescanning(true);
    try {
      const res = await fetch('/api/agent/inspect/scan', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setFormMap(data.form_map || null);
        setRecipe(data.recipe || null);
      }
    } catch (err) {
      console.error('Rescan error:', err);
    } finally {
      setRescanning(false);
    }
  };

  // Send a chat message
  const handleSendChatMessage = async (msgText) => {
    try {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          action: 'SEND_CHAT',
          message: msgText
        }));
      } else {
        const res = await fetch('/api/chat/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msgText })
        });
        if (res.ok) {
          const data = await res.json();
          setChatMessages((prev) => [
            ...prev,
            {
              sender: 'FormPilot',
              text: data.reply,
              time: data.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              action_taken: data.action_taken,
              field_updated: data.field_updated,
              new_value: data.new_value
            }
          ]);
        }
      }
    } catch (err) {
      console.error('Chat error:', err);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-['Plus_Jakarta_Sans',sans-serif]">
      {/* Top navigation */}
      <Header
        agentRunning={agentRunning}
        engineConfig={engineConfig}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenVault={() => setIsVaultOpen(true)}
        onOpenBiometrics={() => setIsBiometricsOpen(true)}
        voiceEnabled={voiceEnabled}
        setVoiceEnabled={setVoiceEnabled}
        currentGate={currentGate}
      />

      {/* Main workspace */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 space-y-4">
        {inspectOpen && (
          <div className="rounded-2xl border border-sky-500/40 bg-sky-500/10 px-4 py-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <ScanSearch className="w-4 h-4 text-sky-300 shrink-0" />
              <div className="min-w-0">
                <div className="text-xs font-bold text-sky-200">
                  Inspect-only session · nothing is being filled, clicked, paid or submitted
                </div>
                <div className="text-[11px] text-sky-300/70">
                  Scroll and click the real portal on the left. Rescan when you reach another step.
                </div>
              </div>
            </div>
            <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded-lg bg-sky-500/15 border border-sky-500/30 text-sky-200">
              {formMap?.field_count || 0} fields mapped
            </span>
          </div>
        )}

        {/* Portal lookup */}
        <PortalLauncher
          onLaunch={handleLaunch}
          agentRunning={agentRunning}
          sessionOpen={busy}
        />

        {/* Center Grid: Live Browser Viewport & Interactive Companion */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Left Column: Live Browser Viewport */}
          <LiveViewport
            screenshot={screenshot}
            liveSession={liveSession}
            agentRunning={agentRunning}
            currentSection={currentSection}
            onStop={handleStop}
            onRescan={handleRescan}
            runMode={runMode}
            runState={runState}
            pendingGate={currentGate && gateHidden ? currentGate : null}
            onOpenGate={() => setGateHidden(false)}
          />

          {/* Right column: chat, activity and the normalized form map */}
          <div className="space-y-3">
            {/* Panel tabs */}
            <div className="flex items-center justify-between p-1 rounded-xl bg-slate-900 border border-slate-800">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setRightTab('chat')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                    rightTab === 'chat'
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span>Ask FormPilot</span>
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                </button>

                <button
                  type="button"
                  onClick={() => setRightTab('map')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                    rightTab === 'map'
                      ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <ScanSearch className="w-3.5 h-3.5" />
                  <span>Page map</span>
                  {formMap && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">
                      {formMap.field_count || 0}
                    </span>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => setRightTab('stream')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                    rightTab === 'stream'
                      ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Terminal className="w-3.5 h-3.5" />
                  <span>Activity</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">
                    {events.length}
                  </span>
                </button>
              </div>

              <div className="text-[11px] font-medium text-slate-500 pr-2 hidden sm:block">
                {rightTab === 'chat'
                  ? 'Questions and saved details'
                  : rightTab === 'map'
                    ? 'Normalized fields and recipes'
                    : 'Step-by-step updates'}
              </div>
            </div>

            {/* Active panel */}
            {rightTab === 'chat' && (
              <LiveChat
                onSendMessage={handleSendChatMessage}
                chatMessages={chatMessages}
                voiceEnabled={voiceEnabled}
              />
            )}
            {rightTab === 'map' && (
              <FormMapPanel
                formMap={formMap}
                recipe={recipe}
                runMode={runMode}
                onRescan={handleRescan}
                rescanning={rescanning}
              />
            )}
            {rightTab === 'stream' && (
              <CognitiveStream
                events={events}
                voiceEnabled={voiceEnabled}
              />
            )}
          </div>
        </div>

      </main>

      {/* Modals and review checkpoints */}
      <HumanCheckpointModal
        activeGate={currentGate}
        hidden={gateHidden}
        onSubmitResponse={handleSubmitUserResponse}
        onClose={() => setGateHidden(true)}
        onDismissGate={handleDismissGate}
        liveSession={liveSession}
        screenshot={screenshot}
      />

      <OneVaultDrawer
        isOpen={isVaultOpen}
        onClose={() => setIsVaultOpen(false)}
      />

      <BiometricsStudio
        isOpen={isBiometricsOpen}
        onClose={() => setIsBiometricsOpen(false)}
      />

      <TinyFishSettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onConfigSaved={(newCfg) => setEngineConfig(newCfg)}
      />

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 px-6 py-4 text-center text-xs text-slate-500">
        <p>
          FormPilot is an independent application assistant. It is not a government website and
          does not submit applications or make payments on your behalf.
        </p>
      </footer>
    </div>
  );
}
