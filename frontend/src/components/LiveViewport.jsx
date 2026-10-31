import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Eye,
  Globe2,
  Maximize2,
  Minimize2,
  MousePointer2,
  Pause,
  Play,
  Power,
  Radio,
  RefreshCw,
  ScanSearch,
  Shield,
  ShieldCheck,
  Sparkles,
  Unplug,
  Wifi,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { getWsUrl } from '../apiConfig';

function wsUrlFor(path) {
  return getWsUrl(path);
}

function displayUrl(url) {
  const value = String(url || '');
  if (!value) return '';
  try {
    const parsed = new URL(value);
    return `${parsed.host}${parsed.pathname}${parsed.search ? '?' + parsed.search.slice(1) : ''}`;
  } catch {
    return value;
  }
}

export default function LiveViewport({
  screenshot,
  liveSession,
  agentRunning,
  currentSection,
  onStop,
  onRescan,
  onPauseToggle,
  onPractice,
  runMode,
  runState,
  paused,
  takeover,
  onTakeover,
  onReturnControl,
  pendingGate,
  onOpenGate,
  className = '',
}) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [frame, setFrame] = useState('');
  const [viewport, setViewport] = useState({ width: 1280, height: 800 });
  const [pageInfo, setPageInfo] = useState({ url: '', title: '' });
  const [zoom, setZoom] = useState(100);
  const [control, setControl] = useState({
    enabled: runMode === 'inspect',
    reason: runMode === 'inspect'
      ? 'Inspect mode: the browser is yours.'
      : 'The agent is driving. You can take over when it pauses.',
  });
  const [connected, setConnected] = useState(false);
  const [inputError, setInputError] = useState('');
  const [frameCount, setFrameCount] = useState(0);
  const [address, setAddress] = useState('');
  const [rescanning, setRescanning] = useState(false);

  const wsRef = useRef(null);
  const imageRef = useRef(null);
  const shellRef = useRef(null);
  const reconnectRef = useRef(null);
  const errorTimerRef = useRef(null);
  const moveRef = useRef({ pending: null, lastSent: 0, raf: null });
  // A page/frame update must not overwrite an address the human is typing.
  const addressEditingRef = useRef(false);
  const wsPath = liveSession?.ws_path || '';

  const flashError = useCallback((message) => {
    setInputError(String(message || 'The live browser could not accept that input.'));
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    errorTimerRef.current = setTimeout(() => setInputError(''), 5000);
  }, []);

  // Connect to the same Chromium page the agent is driving.
  useEffect(() => {
    if (!wsPath) {
      setConnected(false);
      setFrame('');
      return undefined;
    }

    let disposed = false;
    let stopReconnect = false;
    let attempts = 0;
    addressEditingRef.current = false;
    setFrame('');
    setFrameCount(0);
    setControl({
      enabled: runMode === 'inspect',
      reason: runMode === 'inspect'
        ? 'Inspect mode: the browser is yours.'
        : 'The agent is driving. You can take over when it pauses.',
    });

    const connect = () => {
      if (disposed) return;
      let socket;
      try {
        socket = new WebSocket(wsUrlFor(wsPath));
      } catch {
        flashError('The live browser address is not valid.');
        return;
      }
      wsRef.current = socket;

      socket.onopen = () => {
        if (disposed) return;
        setConnected(true);
      };

      socket.onmessage = (event) => {
        if (disposed) return;
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        if (data.type === 'hello') {
          setConnected(true);
          setViewport(data.viewport || { width: 1280, height: 800 });
          setPageInfo({ url: data.url || '', title: data.title || '' });
          setControl({
            enabled: Boolean(data.control_enabled),
            reason: data.control_reason || '',
          });
          if (data.url && !addressEditingRef.current) setAddress(data.url);
          return;
        }
        if (data.type === 'frame' && data.data) {
          setFrame(`data:image/jpeg;base64,${data.data}`);
          if (data.viewport) setViewport(data.viewport);
          if (data.frames_sent !== undefined) setFrameCount(data.frames_sent);
          if (data.url) {
            setPageInfo((previous) => (
              previous.url === data.url ? previous : { ...previous, url: data.url }
            ));
          }
          return;
        }
        if (data.type === 'page') {
          setPageInfo({
            url: data.url || '',
            title: data.title || '',
          });
          if (data.viewport) setViewport(data.viewport);
          if (data.url && !addressEditingRef.current) setAddress(data.url);
          return;
        }
        if (data.type === 'control') {
          setControl({
            enabled: Boolean(data.enabled),
            reason: data.reason || '',
          });
          return;
        }
        if (data.type === 'input_error') {
          flashError(data.error || 'The live browser did not accept that input.');
          if (data.control_enabled === false && data.error) {
            setControl((previous) => ({ ...previous, enabled: false, reason: data.error }));
          }
          return;
        }
        if (data.type === 'closed') {
          stopReconnect = true;
          setConnected(false);
          setControl({ enabled: false, reason: data.message || 'The live session ended.' });
        }
      };

      socket.onclose = () => {
        if (disposed || stopReconnect) return;
        setConnected(false);
        attempts += 1;
        if (attempts > 5) {
          flashError('The live browser connection was lost. Start the portal again or stop the run.');
          return;
        }
        // The session registry may still have the page while a gate is open.
        // Retry a few times rather than dropping the human's view.
        if (reconnectRef.current) clearTimeout(reconnectRef.current);
        reconnectRef.current = setTimeout(() => {
          if (!disposed) connect();
        }, 1800);
      };

      socket.onerror = () => {
        setConnected(false);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          // ignore
        }
      }
      wsRef.current = null;
      if (moveRef.current.raf) clearTimeout(moveRef.current.raf);
      moveRef.current = { pending: null, lastSent: 0, raf: null };
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    };
  }, [wsPath, runMode, flashError]);

  const send = useCallback((payload) => {
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      flashError('The live browser is reconnecting. Try again in a moment.');
      return false;
    }
    try {
      socket.send(JSON.stringify(payload));
      return true;
    } catch {
      flashError('The live browser could not accept that input.');
      return false;
    }
  }, [flashError]);

  const pagePoint = (event) => {
    const image = imageRef.current;
    if (!image) return null;
    const rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const x = ((event.clientX - rect.left) / rect.width) * viewport.width;
    const y = ((event.clientY - rect.top) / rect.height) * viewport.height;
    if (x < 0 || y < 0 || x > viewport.width || y > viewport.height) return null;
    return { x: Math.round(x), y: Math.round(y) };
  };

  const modifiersOf = (event) => ({
    altKey: event.altKey,
    ctrlKey: event.ctrlKey,
    metaKey: event.metaKey,
    shiftKey: event.shiftKey,
  });

  const sendMouse = (event, kind) => {
    if (!control.enabled) return;
    const point = pagePoint(event);
    if (!point) return;
    send({
      type: 'mouse',
      event: kind,
      x: point.x,
      y: point.y,
      button: event.button === 2 ? 'right' : event.button === 1 ? 'middle' : 'left',
      ...modifiersOf(event),
    });
  };

  const handleMouseMove = (event) => {
    if (!control.enabled) return;
    const point = pagePoint(event);
    if (!point) return;
    const state = moveRef.current;
    state.pending = point;
    const now = performance.now();
    if (state.raf) return;
    const wait = Math.max(0, 34 - (now - state.lastSent));
    state.raf = setTimeout(() => {
      state.raf = null;
      const current = moveRef.current.pending;
      if (!current) return;
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(JSON.stringify({ type: 'mouse', event: 'move', x: current.x, y: current.y }));
      moveRef.current.lastSent = performance.now();
    }, wait);
  };

  const handleWheel = useCallback((event) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const point = pagePoint(event);
    if (!point) return;
    event.preventDefault();
    send({
      type: 'wheel',
      x: point.x,
      y: point.y,
      deltaX: event.deltaX,
      deltaY: event.deltaY,
      ...modifiersOf(event),
    });
  }, [send, viewport.width, viewport.height]);

  useEffect(() => {
    const node = shellRef.current;
    if (!node) return undefined;
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => node.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  const handleKeyDown = (event) => {
    if (!control.enabled || event.isComposing) return;
    if (event.key === 'F5' || event.key === 'F12') return;
    event.preventDefault();
    send({
      type: 'key',
      event: 'down',
      key: event.key,
      code: event.code,
      text: event.key.length === 1 ? event.key : undefined,
      ...modifiersOf(event),
    });
  };

  const handleKeyUp = (event) => {
    if (!control.enabled || event.isComposing) return;
    if (event.key === 'F5' || event.key === 'F12') return;
    event.preventDefault();
    send({
      type: 'key',
      event: 'up',
      key: event.key,
      code: event.code,
      ...modifiersOf(event),
    });
  };

  const handlePaste = (event) => {
    if (!control.enabled) return;
    const text = event.clipboardData?.getData('text');
    if (!text) return;
    event.preventDefault();
    send({ type: 'paste', text });
  };

  const requestControl = () => {
    send({ type: 'control_request' });
  };

  const navigate = (kind, extra = {}) => {
    send({ type: kind, ...extra });
  };

  const submitAddress = (event) => {
    event.preventDefault();
    const value = address.trim();
    if (!value) return;
    const url = /^https?:\/\//i.test(value) ? value : `https://${value}`;
    // Keep the human's address visible while the navigation is in flight.
    addressEditingRef.current = false;
    setAddress(url);
    navigate('navigate', { url });
  };

  const handleRescan = async () => {
    if (!onRescan || rescanning) return;
    setRescanning(true);
    try {
      await onRescan();
    } finally {
      setRescanning(false);
    }
  };

  const imageSource = frame || screenshot;
  const live = Boolean(wsPath);
  const canControl = Boolean(connected && control.enabled);
  const active = agentRunning || runState === 'WAITING_FOR_USER';
  const finished = ['STOPPED', 'FAILED', 'COMPLETED', 'DONE'].includes(runState);
  const sessionLabel = runMode === 'inspect'
    ? 'INSPECT · NOTHING WILL BE FILLED'
    : finished
      ? runState === 'DONE'
        ? 'SIGNED IN · BROWSER CLOSED'
        : 'SESSION FINISHED · BROWSER CLOSED'
      : runState === 'AWAITING_PAYMENT'
        ? 'YOUR REVIEW · NOTHING SUBMITTED'
        : takeover?.active
          ? 'HUMAN CONTROL · FORMPILOT PAUSED'
          : active
            ? 'AGENT SESSION · HUMAN TAKEOVER AVAILABLE ANY TIME'
            : 'LIVE PORTAL VIEW';

  return (
    <div
      className={`bg-slate-900 border border-slate-800 rounded-2xl flex flex-col overflow-hidden shadow-xl ${
        isFullscreen ? 'fixed inset-2 z-50 bg-slate-950/95 backdrop-blur-xl border-amber-500/50 md:inset-4' : className || 'h-[640px]'
      }`}
    >
      {/* Browser chrome */}
      <div className="bg-slate-950 px-3 py-2 border-b border-slate-800 shrink-0">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
            </div>
            <span className="text-slate-600 font-mono text-xs shrink-0">|</span>
            <Radio className={`w-3.5 h-3.5 shrink-0 ${connected ? 'text-emerald-400 animate-pulse' : 'text-slate-500'}`} />
            <span className="text-[11px] font-semibold text-slate-300 font-mono tracking-wide truncate">
              {sessionLabel}
            </span>
            {runMode !== 'inspect' && (active || live) && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-800 text-amber-300 border border-slate-700 shrink-0">
                Section {currentSection || 1}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {live && runMode === 'inspect' && (
              <button
                type="button"
                onClick={handleRescan}
                disabled={rescanning}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 border border-sky-500/40 text-[11px] font-bold transition-all disabled:opacity-50"
                title="Read this page again and update the form map"
              >
                <ScanSearch className={`w-3.5 h-3.5 ${rescanning ? 'animate-pulse' : ''}`} />
                <span>{rescanning ? 'Scanning…' : 'Rescan'}</span>
              </button>
            )}
            {takeover?.available && runMode !== 'inspect' && (
              takeover.active ? (
                <button
                  type="button"
                  onClick={onReturnControl}
                  className="flex items-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/15 px-2.5 py-1 text-[11px] font-bold text-sky-300 transition-all hover:bg-sky-500/25"
                  title="Take the page back, re-read it, and stay paused until you continue"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>Return &amp; rescan</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onTakeover}
                  className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/15 px-2.5 py-1 text-[11px] font-bold text-amber-300 transition-all hover:bg-amber-500/25"
                  title="Pause FormPilot and control the real page yourself"
                >
                  <MousePointer2 className="h-3.5 w-3.5" />
                  <span>Take over</span>
                </button>
              )
            )}
            {runMode !== 'inspect' && agentRunning && runState !== 'WAITING_FOR_USER' && onPauseToggle && (
              <button
                type="button"
                onClick={onPauseToggle}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-bold transition-all ${
                  paused
                    ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25'
                    : 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700'
                }`}
                title={paused ? 'Resume the agent' : 'Pause the agent at the next safe point'}
              >
                {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
                <span>{paused ? 'Resume' : 'Pause'}</span>
              </button>
            )}
            {(active || live) && (
              <button
                type="button"
                onClick={onStop}
                className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/40 text-xs font-bold transition-all"
                title={active ? 'Stop the application and close the browser' : 'Close the live browser'}
              >
                <Power className="w-3.5 h-3.5" />
                <span>{active ? 'Stop' : 'Close'}</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
              title={isFullscreen ? 'Exit full screen' : 'Expand view'}
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {live && (
          <div className="flex items-center gap-1.5 mt-2">
            <button
              type="button"
              onClick={() => navigate('back')}
              disabled={!canControl}
              className="p-1.5 rounded-md bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 disabled:opacity-40"
              title="Back"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => navigate('forward')}
              disabled={!canControl}
              className="p-1.5 rounded-md bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 disabled:opacity-40"
              title="Forward"
            >
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => navigate('reload')}
              disabled={!canControl}
              className="p-1.5 rounded-md bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 disabled:opacity-40"
              title="Reload"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <form onSubmit={submitAddress} className="flex-1 min-w-0">
              <div className="relative">
                <Globe2 className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  value={address}
                  onChange={(event) => {
                    addressEditingRef.current = true;
                    setAddress(event.target.value);
                  }}
                  onFocus={() => {
                    addressEditingRef.current = true;
                  }}
                  onBlur={() => {
                    addressEditingRef.current = false;
                    if (!address.trim()) setAddress(pageInfo.url || '');
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      addressEditingRef.current = false;
                      setAddress(pageInfo.url || '');
                      event.currentTarget.blur();
                    }
                  }}
                  disabled={!canControl}
                  spellCheck={false}
                  className="w-full pl-8 pr-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 focus:border-amber-500/70 text-[11px] font-mono text-slate-300 outline-none disabled:opacity-60"
                  placeholder="https://official-portal.gov.in/apply"
                  title={pageInfo.title || displayUrl(pageInfo.url) || 'Live page address'}
                />
              </div>
            </form>
            <span
              className={`flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-md border ${
                canControl
                  ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30'
                  : 'text-amber-300 bg-amber-500/10 border-amber-500/30'
              }`}
              title={control.reason}
            >
              {canControl || takeover?.active ? <MousePointer2 className="w-3 h-3" /> : <Shield className="w-3 h-3" />}
              <span>
                {takeover?.active
                  ? 'You have control'
                  : canControl
                    ? 'You can click and type'
                    : 'Agent has control'}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Real page, streamed over CDP and forwarding input */}
      <div
        ref={shellRef}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onKeyUp={handleKeyUp}
        onPaste={handlePaste}
        onMouseDown={(event) => {
          shellRef.current?.focus();
          sendMouse(event, 'down');
        }}
        onMouseUp={(event) => sendMouse(event, 'up')}
        onMouseMove={handleMouseMove}
        onContextMenu={(event) => event.preventDefault()}
        className={`relative flex-1 bg-slate-950 overflow-auto p-2 outline-none ${
          canControl ? 'cursor-crosshair' : 'cursor-default'
        }`}
      >
        {imageSource ? (
          <div
            className="relative mx-auto transition-[width] duration-200"
            style={{ width: `${zoom}%` }}
          >
            <img
              ref={imageRef}
              src={imageSource}
              alt="Live interactive view of the portal"
              draggable={false}
              className="w-full h-auto rounded-lg border border-slate-800 shadow-2xl select-none"
            />
            {(paused || takeover?.active) && (
              <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-slate-950/90 px-2.5 py-1 text-[10px] font-bold text-amber-300">
                <Pause className="h-3 w-3" />
                {takeover?.active ? 'You have the browser · FormPilot paused' : 'Paused by you'}
              </div>
            )}
            {!connected && live && (
              <div className="absolute top-3 right-3 flex items-center gap-1.5 text-[11px] font-mono px-2 py-1 rounded-md bg-slate-950/90 border border-amber-500/40 text-amber-300">
                <Unplug className="w-3.5 h-3.5" />
                <span>Reconnecting to the live page…</span>
              </div>
            )}
            {active && !paused && !takeover?.active && (
              <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-lg">
                <div className="w-full h-1 bg-gradient-to-r from-transparent via-amber-400/50 to-transparent animate-scanline opacity-75" />
              </div>
            )}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <div className="w-full max-w-md text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900 text-slate-500 shadow-inner">
                <Eye className="h-7 w-7" />
              </div>
              <h3 className="text-sm font-bold text-slate-200">
                {finished ? 'This session has ended' : 'No portal open yet'}
              </h3>
              <p className="mx-auto mt-2 max-w-xs text-xs leading-relaxed text-slate-500">
                {finished
                  ? 'The live browser was closed and nothing was submitted. Your saved details are unchanged — start again whenever you are ready.'
                  : 'The real, interactive browser appears here. Open a portal to fill it with guidance, or use inspect-only to map it without touching anything.'}
              </p>

              <div className="mt-5 grid grid-cols-3 gap-2 text-left">
                <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-2.5">
                  <Globe2 className="h-3.5 w-3.5 text-sky-400" />
                  <div className="mt-1.5 text-[10px] font-bold text-slate-300">Open</div>
                  <div className="text-[9px] leading-tight text-slate-500">Official page loads here</div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-2.5">
                  <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                  <div className="mt-1.5 text-[10px] font-bold text-slate-300">Fill</div>
                  <div className="text-[9px] leading-tight text-slate-500">Profile values, step by step</div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-2.5">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                  <div className="mt-1.5 text-[10px] font-bold text-slate-300">Review</div>
                  <div className="text-[9px] leading-tight text-slate-500">You handle checks and submit</div>
                </div>
              </div>

              {onPractice && (
                <button
                  type="button"
                  onClick={onPractice}
                  className="mt-5 inline-flex items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/15 px-4 py-2 text-xs font-bold text-amber-300 transition-colors hover:bg-amber-500/25"
                >
                  <Play className="h-3.5 w-3.5" />
                  Try the practice portal
                </button>
              )}
            </div>
          </div>
        )}

        {inputError && (
          <div className="sticky bottom-2 left-2 right-2 z-10 mx-auto max-w-lg rounded-xl bg-red-950/95 border border-red-500/50 px-3 py-2 text-[11px] text-red-200 shadow-xl">
            {inputError}
          </div>
        )}

        {pendingGate && (
          <button
            type="button"
            onClick={onOpenGate}
            className="absolute bottom-3 right-3 z-10 flex items-center gap-2 rounded-xl bg-amber-500 hover:bg-amber-400 px-4 py-2.5 text-xs font-extrabold text-slate-950 shadow-xl"
          >
            <Shield className="w-4 h-4" />
            <span>Checkpoint needs you</span>
          </button>
        )}
      </div>

      {/* Status footer */}
      <div className="bg-slate-950/80 px-4 py-2 border-t border-slate-800/80 text-[11px] text-slate-500 flex flex-wrap items-center justify-between gap-2 font-mono">
        <div className="flex items-center gap-3 min-w-0">
          <span className="flex items-center gap-1.5">
            {connected ? <Wifi className="w-3.5 h-3.5 text-emerald-400" /> : <Unplug className="w-3.5 h-3.5 text-slate-500" />}
            {connected ? 'live page stream' : live ? 'disconnected' : finished ? 'session closed' : 'viewer only'}
          </span>
          <span>•</span>
          <span className="truncate" title={pageInfo.url || ''}>
            {displayUrl(pageInfo.url) || (runMode === 'inspect' ? 'Inspect-only browser' : 'Waiting for a portal')}
          </span>
          {frameCount > 0 && (
            <>
              <span>•</span>
              <span>{frameCount.toLocaleString()} frames</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          {imageSource && (
            <div className="flex items-center gap-0.5 rounded-md border border-slate-800 bg-slate-900 p-0.5">
              <button
                type="button"
                onClick={() => setZoom((value) => Math.max(50, value - 25))}
                disabled={zoom <= 50}
                className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200 disabled:opacity-30"
                title="Zoom out"
              >
                <ZoomOut className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => setZoom(100)}
                className="min-w-[38px] rounded px-1 text-[10px] font-bold text-slate-400 hover:text-slate-200"
                title="Reset zoom"
              >
                {zoom}%
              </button>
              <button
                type="button"
                onClick={() => setZoom((value) => Math.min(200, value + 25))}
                disabled={zoom >= 200}
                className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200 disabled:opacity-30"
                title="Zoom in"
              >
                <ZoomIn className="h-3 w-3" />
              </button>
            </div>
          )}
          {!canControl && !takeover?.active && live && (
            <button
              type="button"
              onClick={takeover?.available ? onTakeover : requestControl}
              className="text-[10px] font-bold text-amber-300 hover:text-amber-200 underline decoration-dotted"
              title={takeover?.available ? 'Pause FormPilot and control the page' : control.reason}
            >
              {takeover?.available ? 'Take over the browser' : 'Request control'}
            </button>
          )}
          <span className="flex items-center gap-1.5 text-slate-400">
            <Shield className="w-3.5 h-3.5 text-amber-500" />
            <span>Never pays or submits for you</span>
          </span>
        </div>
      </div>
    </div>
  );
}
