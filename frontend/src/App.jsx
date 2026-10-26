import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import PortalLauncher from './components/PortalLauncher';
import LiveViewport from './components/LiveViewport';
import CognitiveStream from './components/CognitiveStream';
import LiveChat from './components/LiveChat';
import HumanCheckpointModal from './components/HumanCheckpointModal';
import OneVaultDrawer from './components/OneVaultDrawer';
import BiometricsStudio from './components/BiometricsStudio';
import TinyFishSettingsModal from './components/TinyFishSettingsModal';
import { MessageSquare, Terminal } from 'lucide-react';

export default function App() {
  const [agentRunning, setAgentRunning] = useState(false);
  const [events, setEvents] = useState([]);
  const [screenshot, setScreenshot] = useState('');
  const [currentGate, setCurrentGate] = useState(null);
  const [currentSection, setCurrentSection] = useState(1);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [rightTab, setRightTab] = useState('chat'); // 'chat' | 'stream'
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

  // Initialize WebSocket connection and global key listeners
  useEffect(() => {
    connectWebSocket();
    fetchEngineConfig();

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setCurrentGate(null);
        fetch('/api/agent/dismiss-gate', { method: 'POST' }).catch(() => {});
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
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
          setEvents((prev) => [...prev, data]);
        }

        // Update live screenshot
        if (data.screenshot) {
          setScreenshot(data.screenshot);
        }

        // Update active gate
        if (data.active_gate !== undefined) {
          setCurrentGate(data.active_gate);
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

        // Infer running status
        if (data.active_gate?.gate_type === 'PRE_PAYMENT_SAFETY_LOCK') {
          setAgentRunning(false);
        }
      } catch (err) {
        console.error('[Cockpit WS] Parse error:', err);
      }
    };

    ws.onclose = () => {
      console.log('[Cockpit WS] Disconnected. Reconnecting in 2s...');
      setTimeout(connectWebSocket, 2000);
    };
  };

  // Launch Agent
  const handleLaunch = async (queryOrUrl) => {
    setEvents([]);
    setCurrentGate(null);
    setAgentRunning(true);
    try {
      const res = await fetch('/api/agent/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_or_url: queryOrUrl })
      });
      const data = await res.json();
      if (!data.success) {
        alert(data.message || 'Could not start application sequence.');
        setAgentRunning(false);
      }
    } catch (err) {
      console.error('Launch error:', err);
      setAgentRunning(false);
    }
  };

  // Emergency Stop Agent
  const handleStop = async () => {
    try {
      await fetch('/api/agent/stop', { method: 'POST' });
      setAgentRunning(false);
      setCurrentGate(null);
    } catch (err) {
      console.error('Stop error:', err);
    }
  };

  // Submit Candidate Gate Response
  const handleSubmitUserResponse = async (payload) => {
    try {
      // Clear active gate locally first for instant feedback
      setCurrentGate(null);
      await fetch('/api/agent/user-response', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (err) {
      console.error('User response submission error:', err);
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
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 space-y-6">
        
        {/* Portal lookup */}
        <PortalLauncher
          onLaunch={handleLaunch}
          agentRunning={agentRunning}
        />

        {/* Center Grid: Live Browser Viewport & Interactive Companion */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Left Column: Live Browser Viewport */}
          <LiveViewport
            screenshot={screenshot}
            agentRunning={agentRunning}
            currentSection={currentSection}
            onStop={handleStop}
          />

          {/* Right column: chat and activity */}
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
                {rightTab === 'chat' ? 'Questions and saved details' : 'Step-by-step updates'}
              </div>
            </div>

            {/* Active panel */}
            {rightTab === 'chat' ? (
              <LiveChat
                onSendMessage={handleSendChatMessage}
                chatMessages={chatMessages}
                voiceEnabled={voiceEnabled}
              />
            ) : (
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
        onSubmitResponse={handleSubmitUserResponse}
        onClose={() => setCurrentGate(null)}
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
