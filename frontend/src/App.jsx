import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import SessionStrip from './components/SessionStrip';
import Toasts from './components/Toasts';
import { AlertTriangle, MessageSquare, ScanSearch, Terminal } from 'lucide-react';

const ACTIVE_STATES = new Set(['RESOLVING', 'RUNNING', 'WAITING_FOR_USER', 'PAUSED']);
const TERMINAL_STATES = new Set(['STOPPED', 'FAILED', 'COMPLETED', 'AWAITING_PAYMENT', 'DONE']);

function formatElapsed(startedAt) {
  if (!startedAt) return '00:00';
  const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  const hours = Math.floor(minutes / 60);
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
}

function startedAtFromRunId(runId) {
  const match = /^run-(\d{8})-(\d{6})-/.exec(runId || '');
  if (!match) return null;
  const [, date, time] = match;
  const parsed = new Date(
    Number(date.slice(0, 4)),
    Number(date.slice(4, 6)) - 1,
    Number(date.slice(6, 8)),
    Number(time.slice(0, 2)),
    Number(time.slice(2, 4)),
    Number(time.slice(4, 6))
  );
  return Number.isNaN(parsed.getTime()) ? null : parsed.getTime();
}

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
  const [fillSummary, setFillSummary] = useState(null);
  const [fillFailures, setFillFailures] = useState([]);
  const [entryMode, setEntryMode] = useState(null);
  const [entryOptions, setEntryOptions] = useState([]);
  const [loginMethod, setLoginMethod] = useState(null);
  const [loginIdentifier, setLoginIdentifier] = useState(null);
  const [rescanning, setRescanning] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [rightTab, setRightTab] = useState('chat'); // 'chat' | 'stream' | 'map'
  const [chatMessages, setChatMessages] = useState([]);
  const [vault, setVault] = useState(null);
  const [query, setQuery] = useState('');
  const [runId, setRunId] = useState(null);
  const [lastError, setLastError] = useState('');
  const [startedAt, setStartedAt] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [now, setNow] = useState(Date.now());

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
  const toastIdRef = useRef(0);
  const previousStateRef = useRef('IDLE');

  const agentRunning = ACTIVE_STATES.has(runState);
  const inspectOpen = runState === 'INSPECT_READY' && Boolean(liveSession);
  const paused = runState === 'PAUSED';
  const sessionVisible = agentRunning || inspectOpen || runState === 'AWAITING_PAYMENT' || TERMINAL_STATES.has(runState);
  const relaunchable = ['STOPPED', 'FAILED', 'COMPLETED', 'DONE'].includes(runState);
  const started = agentRunning || inspectOpen || runState === 'AWAITING_PAYMENT';
  const terminal = TERMINAL_STATES.has(runState);

  const readiness = useMemo(() => {
    if (!vault) return null;
    const checks = [
      vault.full_name,
      vault.dob,
      vault.gender,
      vault.mobile,
      vault.email,
      vault.address_line_1 || vault.village_town_city,
      vault.district,
      vault.state,
      vault.pincode,
      vault.matric?.roll_number,
      vault.intermediate?.roll_number,
      vault.photo_path,
      vault.signature_path,
    ];
    const total = checks.length;
    const filled = checks.filter((value) => value !== null && value !== undefined && String(value).trim() !== '').length;
    return { filled, total, percent: Math.round((filled / total) * 100) };
  }, [vault]);

  const elapsed = useMemo(
    () => formatElapsed(startedAt || startedAtFromRunId(runId)),
    [startedAt, runId, now]
  );
  const busy = agentRunning || inspectOpen;

  const notify = useCallback((message, tone = 'info') => {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((previous) => [...previous.slice(-3), { id, message, tone }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((previous) => previous.filter((toast) => toast.id !== id));
  }, []);

  const fetchVault = useCallback(async () => {
    try {
      const res = await fetch('/api/vault');
      if (res.ok) {
        setVault(await res.json());
      }
    } catch (err) {
      console.error('Vault fetch error:', err);
    }
  }, []);

  // Keep the elapsed timer moving only while the agent is active.
  useEffect(() => {
    if (!started) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [started]);

  // Refresh saved details whenever the vault drawer closes.
  useEffect(() => {
    if (!isVaultOpen) fetchVault();
  }, [isVaultOpen, fetchVault]);

  // Initialize WebSocket connection, agent state and global key listeners
  useEffect(() => {
    currentGateRef.current = currentGate;
  }, [currentGate]);

  useEffect(() => {
    connectWebSocket();
    fetchEngineConfig();
    fetchAgentState();
    fetchVault();

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
      setFillSummary(data.fill_summary || null);
      setFillFailures(data.fill_failures || []);
      setEntryMode(data.entry_mode || null);
      setEntryOptions(data.entry_options || []);
      setLoginMethod(data.login_method || null);
      setLoginIdentifier(data.login_identifier || null);
      setCurrentSection(data.current_section || 1);
      setQuery(data.query || '');
      setRunId(data.run_id || null);
      setLastError(data.last_error || '');
      if (ACTIVE_STATES.has(data.state) && data.run_id) {
        setStartedAt(startedAtFromRunId(data.run_id) || Date.now());
      }
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
          if (data.state === 'FAILED' && previousStateRef.current !== 'FAILED') {
            notify('The application hit an error. Review the activity log and try again.', 'error');
          }
          if (data.state === 'WAITING_FOR_USER' && previousStateRef.current !== 'WAITING_FOR_USER') {
            notify('A checkpoint needs your input.', 'info');
          }
          previousStateRef.current = data.state;
          setRunState(data.state);
          if (ACTIVE_STATES.has(data.state) || data.state === 'INSPECT_READY') {
            setStartedAt((previous) => previous ?? (startedAtFromRunId(data.run_id) || Date.now()));
          } else {
            setStartedAt(null);
          }
        }
        if (data.run_id) {
          setRunId(data.run_id);
        }
        if (data.last_error) {
          setLastError(data.last_error);
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
        if ('fill_summary' in data) {
          setFillSummary(data.fill_summary || null);
        }
        if ('fill_failures' in data) {
          setFillFailures(data.fill_failures || []);
        }
        if ('entry_mode' in data) {
          setEntryMode(data.entry_mode || null);
        }
        if ('entry_options' in data) {
          setEntryOptions(data.entry_options || []);
        }
        if ('login_method' in data) {
          setLoginMethod(data.login_method || null);
        }
        if ('login_identifier' in data) {
          setLoginIdentifier(data.login_identifier || null);
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
              new_value: data.new_value,
              entry_mode: data.entry_mode,
              login_method: data.login_method,
              login_identifier: data.login_identifier
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
    setFillSummary(null);
    setFillFailures([]);
    setEntryMode(null);
    setEntryOptions([]);
    setLoginMethod(null);
    setLoginIdentifier(null);
    setChatMessages([]);
    setRunMode(mode);
    setRunState('RESOLVING');
    setQuery(queryOrUrl);
    setStartedAt(Date.now());
    setNow(Date.now());
    setLastError('');
    try {
      const res = await fetch('/api/agent/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_or_url: queryOrUrl, mode })
      });
      const data = await res.json();
      if (!data.success) {
        notify(data.message || 'Could not start the application sequence.', 'error');
        setRunState('IDLE');
        setStartedAt(null);
      } else {
        setRunId(data.run_id || null);
        notify(mode === 'inspect' ? 'Inspect-only session started.' : 'Application started.', 'success');
      }
    } catch (err) {
      console.error('Launch error:', err);
      notify('Could not reach the FormPilot backend. Check that the app is running.', 'error');
      setRunState('FAILED');
      setStartedAt(null);
    }
  };

  const handlePractice = () => {
    handleLaunch('http://127.0.0.1:8000/gov-portal-demo', 'fill');
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
    setStartedAt(null);
    notify('Session stopped. The browser was closed.', 'info');
  };

  const handleNewSession = async () => {
    try {
      await fetch('/api/agent/reset', { method: 'POST' });
    } catch (err) {
      console.error('Session reset error:', err);
    }
    setRunState('IDLE');
    setRunMode('fill');
    setCurrentGate(null);
    setGateHidden(false);
    setLiveSession(null);
    setScreenshot('');
    setFormMap(null);
    setRecipe(null);
    setEvents([]);
    setChatMessages([]);
    setCurrentSection(1);
    setQuery('');
    setRunId(null);
    setLastError('');
    setStartedAt(null);
    previousStateRef.current = 'IDLE';
    gateKeyRef.current = '';
  };

  const handlePauseToggle = async () => {
    const wasPaused = runState === 'PAUSED';
    try {
      const res = await fetch(wasPaused ? '/api/agent/resume' : '/api/agent/pause', {
        method: 'POST',
      });
      const data = await res.json();
      if (!data.success) {
        notify(data.message || 'That action is not available right now.', 'error');
        return;
      }
      setRunState(data.state || (wasPaused ? 'RUNNING' : 'PAUSED'));
      notify(wasPaused ? 'Application resumed.' : 'Paused. The agent will wait for you.', 'info');
    } catch (err) {
      console.error('Pause/resume error:', err);
      notify('Could not change the application state. Try again.', 'error');
    }
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
      notify('Your response could not be sent. Please try again.', 'error');
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
        notify('Page mapped again.', 'success');
      } else {
        notify('Rescan failed. Make sure the live browser is still open.', 'error');
      }
    } catch (err) {
      console.error('Rescan error:', err);
      notify('Could not rescan this page.', 'error');
    } finally {
      setRescanning(false);
    }
  };

  // Send a chat message. The candidate's message is stored locally first so the
  // conversation stays intact while the WebSocket reply is in flight.
  const handleSendChatMessage = async (msgText) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setChatMessages((prev) => [...prev, { sender: 'Candidate', text: msgText, time }]);
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
              time: data.timestamp || time,
              action_taken: data.action_taken,
              field_updated: data.field_updated,
              new_value: data.new_value,
              entry_mode: data.entry_mode,
              login_method: data.login_method,
              login_identifier: data.login_identifier
            }
          ]);
        } else {
          notify('FormPilot could not answer that message.', 'error');
        }
      }
    } catch (err) {
      console.error('Chat error:', err);
      notify('The message could not be sent.', 'error');
    }
  };

  useEffect(() => {
    if (runState === 'INSPECT_READY') setRightTab('map');
  }, [runState]);

  const viewportHeightClass = sessionVisible
    ? 'h-[560px] sm:h-[620px] lg:h-[calc(100vh-278px)] lg:min-h-[560px] lg:max-h-[900px]'
    : 'h-[520px] sm:h-[580px] lg:h-[calc(100vh-470px)] lg:min-h-[480px] lg:max-h-[760px]';

  const panels = [
    {
      id: 'chat',
      label: 'Ask FormPilot',
      icon: MessageSquare,
      count: null,
      hint: 'Questions and saved details',
      activeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    },
    {
      id: 'map',
      label: 'Page map',
      icon: ScanSearch,
      count: (formMap?.field_count || 0) + (formMap?.gateways?.length || 0),
      hint: 'Fields, locators and recipes',
      activeClass: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
    },
    {
      id: 'stream',
      label: 'Activity',
      icon: Terminal,
      count: events.length,
      hint: 'Step-by-step updates',
      activeClass: 'bg-violet-500/20 text-violet-300 border-violet-500/40',
    },
  ];

  return (
    <div className="relative flex min-h-screen flex-col bg-slate-950 font-['Plus_Jakarta_Sans',sans-serif] text-slate-100">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_70%_50%_at_50%_-10%,rgba(245,158,11,0.07),transparent),radial-gradient(ellipse_50%_40%_at_100%_100%,rgba(14,165,233,0.05),transparent)]" />

      <Header
        agentRunning={agentRunning}
        paused={paused}
        runState={runState}
        engineConfig={engineConfig}
        readiness={readiness}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenVault={() => setIsVaultOpen(true)}
        onOpenBiometrics={() => setIsBiometricsOpen(true)}
        onPauseToggle={handlePauseToggle}
        voiceEnabled={voiceEnabled}
        setVoiceEnabled={setVoiceEnabled}
        currentGate={currentGate}
      />

      <main className="relative mx-auto flex w-full max-w-[1560px] flex-1 flex-col px-3 pb-8 pt-4 sm:px-5">
        {sessionVisible && (
          <SessionStrip
            runState={runState}
            runMode={runMode}
            currentSection={currentSection}
            formMap={formMap}
            recipe={recipe}
            readiness={readiness}
            query={query}
            targetUrl={liveSession?.url || formMap?.url || ''}
            elapsed={elapsed}
            paused={paused}
            runId={runId}
            fillSummary={fillSummary}
            entryMode={entryMode}
            loginMethod={loginMethod}
            onPauseToggle={handlePauseToggle}
            onNewSession={handleNewSession}
          />
        )}

        {(!sessionVisible || relaunchable) && (
          <div className={sessionVisible ? 'mt-4' : ''}>
            <PortalLauncher
              onLaunch={handleLaunch}
              agentRunning={agentRunning}
              sessionOpen={busy}
            />
          </div>
        )}

        {lastError && (
          <div className="mt-3 rounded-xl border border-red-500/35 bg-red-500/10 px-3.5 py-2.5 text-[11px] text-red-200">
            <span className="font-bold">Last issue:</span> {lastError}
          </div>
        )}

        {['PARTIAL', 'FAILED'].includes(fillSummary?.status) && (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3.5 py-2.5 text-[11px] text-amber-100">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <span>
              <span className="font-bold">This form is not fully filled.</span>{' '}
              {fillSummary?.verified || 0} of {fillSummary?.attempted || 0} fields were verified
              {fillSummary?.failed ? `, ${fillSummary.failed} failed` : ''}
              {fillSummary?.skipped ? `, ${fillSummary.skipped} skipped` : ''}. Review the
              highlighted fields in the live browser; FormPilot will not report this section as
              filled.
            </span>
          </div>
        )}

        <div className="mt-4 grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(380px,430px)]">
          <LiveViewport
            className={viewportHeightClass}
            screenshot={screenshot}
            liveSession={liveSession}
            agentRunning={agentRunning}
            currentSection={currentSection}
            onStop={handleStop}
            onRescan={handleRescan}
            onPauseToggle={handlePauseToggle}
            onPractice={handlePractice}
            runMode={runMode}
            runState={runState}
            paused={paused}
            pendingGate={currentGate && gateHidden ? currentGate : null}
            onOpenGate={() => setGateHidden(false)}
          />

          <div className={`flex flex-col gap-3 ${viewportHeightClass}`}>
            <div className="flex shrink-0 flex-col gap-2 rounded-2xl border border-slate-800 bg-slate-900 p-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-1 overflow-x-auto no-scrollbar">
                {panels.map((panel) => {
                  const Icon = panel.icon;
                  const active = rightTab === panel.id;
                  return (
                    <button
                      key={panel.id}
                      type="button"
                      onClick={() => setRightTab(panel.id)}
                      className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-bold transition-all ${
                        active
                          ? panel.activeClass
                          : 'border-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      <span>{panel.label}</span>
                      {panel.count !== null && (
                        <span className={`rounded px-1 font-mono text-[9px] ${active ? 'bg-slate-950/40' : 'bg-slate-800 text-slate-500'}`}>
                          {panel.count}
                        </span>
                      )}
                      {panel.id === 'chat' && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="min-h-0 flex-1">
              {rightTab === 'chat' && (
                <LiveChat
                  onSendMessage={handleSendChatMessage}
                  chatMessages={chatMessages}
                  voiceEnabled={voiceEnabled}
                  onClearChat={() => setChatMessages([])}
                  entryMode={entryMode}
                  entryOptions={entryOptions}
                  loginMethod={loginMethod}
                  loginIdentifier={loginIdentifier}
                  activeGate={currentGate}
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
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 px-1 text-[10px] text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            FormPilot never solves CAPTCHA, auto-pays or submits on your behalf.
          </span>
          <span className="font-mono text-slate-600">
            {runId ? `session ${runId}` : 'No active run'}
          </span>
        </div>
      </main>

      <footer className="relative border-t border-slate-900 bg-slate-950/80 px-4 py-3.5 text-center text-[11px] text-slate-500">
        <p>
          FormPilot is an independent application assistant. It is not a government website and
          does not submit applications or make payments on your behalf.
        </p>
      </footer>

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

      <Toasts toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
