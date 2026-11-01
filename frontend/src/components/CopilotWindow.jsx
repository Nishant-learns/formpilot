import React, { useState, useEffect, useRef } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  GripHorizontal,
  Maximize2,
  Minimize2,
  Move,
  Pin,
  PinOff,
  Sparkles,
  X,
} from 'lucide-react';
import LiveChat from './LiveChat';
import PageBriefPanel from './PageBriefPanel';
import FormMapPanel from './FormMapPanel';
import CognitiveStream from './CognitiveStream';
import { NeuralSparkleIcon } from './CustomIcons';

export default function CopilotWindow({
  mode = 'docked', // 'docked' | 'floating'
  minimized = false,
  onToggleMode,
  onToggleMinimize,
  onClose,
  rightTab,
  setRightTab,
  panels,
  // LiveChat props
  onSendMessage,
  chatMessages,
  voiceEnabled,
  onClearChat,
  entryMode,
  entryOptions,
  loginMethod,
  loginIdentifier,
  activeGate,
  // PageBrief props
  pageBrief,
  runState,
  onRefreshBrief,
  briefRefreshing,
  // FormMap props
  formMap,
  recipe,
  runMode,
  onRescan,
  rescanning,
  // CognitiveStream props
  events,
}) {
  const [position, setPosition] = useState({
    x: typeof window !== 'undefined' ? Math.max(20, window.innerWidth - 440) : 800,
    y: 80,
  });
  const [size, setSize] = useState({ width: 410, height: 600 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });

  // Floating window drag handlers
  const handleMouseDown = (e) => {
    if (mode !== 'floating') return;
    if (e.target.closest('button') || e.target.closest('input') || e.target.closest('select')) return;
    setIsDragging(true);
    dragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      startX: position.x,
      startY: position.y,
    };
  };

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e) => {
      const dx = e.clientX - dragStartRef.current.mouseX;
      const dy = e.clientY - dragStartRef.current.mouseY;
      const maxX = Math.max(10, window.innerWidth - size.width - 10);
      const maxY = Math.max(10, window.innerHeight - 120);
      setPosition({
        x: Math.max(10, Math.min(maxX, dragStartRef.current.startX + dx)),
        y: Math.max(10, Math.min(maxY, dragStartRef.current.startY + dy)),
      });
    };
    const handleMouseUp = () => {
      setIsDragging(false);
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, size.width]);

  // MINIMIZED STATE HANDLING
  if (minimized) {
    if (mode === 'docked') {
      return (
        <div className="h-full flex flex-col items-center justify-between py-3.5 select-none bg-slate-950/80 w-14 border-l border-white/[0.08]">
          <div className="flex flex-col items-center gap-2.5">
            <button
              type="button"
              onClick={onToggleMinimize}
              className="w-9 h-9 rounded-xl bg-indigo-500/15 hover:bg-indigo-500/25 border border-indigo-500/30 flex items-center justify-center text-indigo-400 hover:text-white transition-all shadow-sm group"
              title="Expand RHS Copilot Panel"
            >
              <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
            </button>

            <div className="w-6 h-px bg-white/[0.08] my-1" />

            {panels.map((p) => {
              const Icon = p.icon;
              const active = rightTab === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    setRightTab(p.id);
                    onToggleMinimize();
                  }}
                  className={`relative w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                    active
                      ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]'
                  }`}
                  title={`${p.label}: ${p.hint}`}
                >
                  <Icon className="w-4 h-4" />
                  {active && (
                    <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-indigo-400" />
                  )}
                </button>
              );
            })}
          </div>

          <div className="flex flex-col items-center gap-2">
            <button
              type="button"
              onClick={onToggleMode}
              className="w-8 h-8 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.06] flex items-center justify-center transition-colors"
              title="Pop out into floating window"
            >
              <PinOff className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="fixed bottom-6 right-6 z-50 animate-fadeIn">
        <button
          type="button"
          onClick={onToggleMinimize}
          className="flex items-center gap-2.5 px-4 py-2.5 rounded-full bg-slate-900/90 hover:bg-slate-800/90 text-white border border-indigo-500/40 shadow-2xl backdrop-blur-xl group transition-all glow-indigo"
        >
          <div className="w-6 h-6 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-400">
            <NeuralSparkleIcon className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-white">AI Copilot Active</span>
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] text-indigo-300 font-mono group-hover:translate-x-0.5 transition-transform">
            [Expand ↗]
          </span>
        </button>
      </div>
    );
  }

  const containerClasses =
    mode === 'floating'
      ? 'fixed z-40 glass-panel-elevated specular-top rounded-3xl border border-white/[0.14] shadow-2xl overflow-hidden flex flex-col glow-indigo animate-fadeIn'
      : 'flex flex-col h-full w-full overflow-hidden';

  const containerStyle =
    mode === 'floating'
      ? {
          left: `${position.x}px`,
          top: `${position.y}px`,
          width: `${size.width}px`,
          height: `${size.height}px`,
          minWidth: '320px',
          minHeight: '400px',
          resize: 'both',
          overflow: 'hidden',
        }
      : {};

  return (
    <div className={containerClasses} style={containerStyle}>
      {/* Floating Window Title Bar with Drag Handle and Window Controls */}
      <div
        onMouseDown={handleMouseDown}
        className={`px-3 py-2 border-b border-white/[0.08] flex items-center justify-between gap-2 select-none shrink-0 ${
          mode === 'floating'
            ? 'bg-gradient-to-r from-slate-950 via-slate-900 to-indigo-950/40 cursor-move'
            : 'glass-panel rounded-2xl p-1.5'
        }`}
      >
        {mode === 'floating' && (
          <div className="flex items-center gap-2 min-w-0">
            <GripHorizontal className="w-4 h-4 text-slate-500 shrink-0" />
            <div className="flex items-center gap-1.5 min-w-0">
              <NeuralSparkleIcon className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
              <span className="text-xs font-extrabold text-white truncate">AI Copilot</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
            </div>
          </div>
        )}

        {/* Navigation Tabs (Copilot, Brief, Map, Cognition) */}
        <div className={`flex items-center gap-1 overflow-x-auto no-scrollbar ${mode === 'floating' ? 'flex-1 max-w-xs justify-end' : 'w-full'}`}>
          {panels.map((panel) => {
            const Icon = panel.icon;
            const active = rightTab === panel.id;
            return (
              <button
                key={panel.id}
                type="button"
                onClick={() => setRightTab(panel.id)}
                className={`flex items-center justify-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs font-bold transition-all shrink-0 ${
                  active
                    ? 'border-indigo-500/40 bg-indigo-500/20 text-indigo-200 shadow-sm'
                    : 'border-transparent text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'
                }`}
                title={panel.hint}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{panel.label}</span>
                {panel.count !== null && (
                  <span
                    className={`rounded-full px-1.5 py-0.2 font-mono text-[9px] ${
                      active ? 'bg-indigo-950/80 text-indigo-300' : 'bg-white/[0.05] text-slate-500'
                    }`}
                  >
                    {panel.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Window Controls: Dock/Undock, Minimize */}
        <div className="flex items-center gap-1 shrink-0 ml-1">
          <button
            type="button"
            onClick={onToggleMode}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.08] transition-colors"
            title={mode === 'floating' ? 'Dock to right sidebar' : 'Pop out into draggable floating window'}
          >
            {mode === 'floating' ? <Pin className="w-3.5 h-3.5" /> : <PinOff className="w-3.5 h-3.5" />}
          </button>
          <button
            type="button"
            onClick={onToggleMinimize}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.08] transition-colors"
            title={mode === 'docked' ? 'Collapse RHS panel' : 'Minimize to floating pill'}
          >
            {mode === 'docked' ? <ChevronRight className="w-3.5 h-3.5" /> : <Minimize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Main Tab Panels Body */}
      <div className={`min-h-0 flex-1 overflow-hidden ${mode === 'floating' ? 'p-3' : ''}`}>
        {rightTab === 'chat' && (
          <LiveChat
            onSendMessage={onSendMessage}
            chatMessages={chatMessages}
            voiceEnabled={voiceEnabled}
            onClearChat={onClearChat}
            entryMode={entryMode}
            entryOptions={entryOptions}
            loginMethod={loginMethod}
            loginIdentifier={loginIdentifier}
            activeGate={activeGate}
          />
        )}
        {rightTab === 'brief' && (
          <PageBriefPanel
            pageBrief={pageBrief}
            runState={runState}
            onRefresh={onRefreshBrief}
            refreshing={briefRefreshing}
          />
        )}
        {rightTab === 'map' && (
          <FormMapPanel
            formMap={formMap}
            recipe={recipe}
            runMode={runMode}
            onRescan={onRescan}
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
  );
}
