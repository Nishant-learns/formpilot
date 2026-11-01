import React, { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Send,
  Sparkles,
  CheckCircle2,
  Trash2,
  PauseCircle,
  PlayCircle,
  Search,
  Clock,
} from 'lucide-react';

const WELCOME = {
  sender: 'FormPilot',
  text: "Hi! I'm here while you fill this application. Ask me about a document or a step, or tell me a saved detail you want to correct. You can also ask me to pause or show your progress.",
  time: 'Now',
  action_taken: 'GREETING',
};

export default function LiveChat({
  onSendMessage,
  chatMessages,
  voiceEnabled,
  onClearChat,
  entryMode,
  entryOptions,
  loginMethod,
  loginIdentifier,
  activeGate,
}) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiConfigured, setAiConfigured] = useState(null);
  const scrollRef = useRef(null);
  const lastSpokenRef = useRef(WELCOME.text);

  const messages = chatMessages?.length ? chatMessages : [WELCOME];

  useEffect(() => {
    let cancelled = false;
    fetch('/api/chat/config')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) setAiConfigured(Boolean(data.configured));
      })
      .catch(() => {
        if (!cancelled) setAiConfigured(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    if (!voiceEnabled || !messages.length) return;
    const latest = messages[messages.length - 1];
    if (latest.sender === 'Candidate') return;
    if (!latest.text || latest.text === lastSpokenRef.current) return;
    if (!('speechSynthesis' in window)) return;

    lastSpokenRef.current = latest.text;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(latest.text);
      utterance.lang = 'hi-IN';
      utterance.rate = 1.05;
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      // Voice is optional; text is always available.
    }
  }, [messages, voiceEnabled]);

  const handleSend = async (textToSend) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    setInput('');
    setLoading(true);
    try {
      if (onSendMessage) {
        await onSendMessage(text);
      }
    } catch (err) {
      console.error('Chat send error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const quickChips = [
    { label: 'Documents I need', query: 'Which documents do I need for this application?' },
    { label: 'Update my date of birth', query: 'Change my date of birth to 15/08/2004' },
    { label: 'Photo requirements', query: 'What are the photo and signature requirements?' },
    { label: 'Is the fee refundable?', query: 'Is the application fee refundable?' },
    { label: 'Pause the application', query: 'Pause the application' },
    { label: 'Show my progress', query: 'What is my current status?' },
  ];

  const gateType = activeGate?.gate_type || '';
  const gateOptions = activeGate?.options || [];
  const entryNeeded = gateType === 'GATEWAY_DECISION' || (!entryMode && (entryOptions?.length || 0) > 0);
  const entryChoices = gateType === 'GATEWAY_DECISION'
    ? gateOptions
    : (entryOptions || []);
  const entryChips = entryNeeded
    ? entryChoices.slice(0, 4).map((option) => ({
        label: option.text || option.mode || option.type || 'Entry path',
        query: option.text || option.mode || option.type,
      }))
    : [];
  const loginChips = gateType === 'LOGIN_METHOD'
    ? gateOptions.slice(0, 4).map((option) => ({
        label: option.label || option.text || option.method,
        query: option.label || option.text || option.method,
      }))
    : [];
  const identifierChips = gateType === 'ACCOUNT_IDENTIFIER'
    ? gateOptions.slice(0, 4).map((option) => ({
        label: option.text || option.key,
        query: option.text || option.key,
      }))
    : [];
  const fillChips = gateType === 'FILL_INCOMPLETE'
    ? [
        { label: 'Recheck fields', query: 'Recheck the fields and fill again' },
        { label: 'Continue after review', query: 'Continue after reviewing the form' },
      ]
    : [];
  const gateChips = [...fillChips, ...entryChips, ...loginChips, ...identifierChips];
  const chips = gateChips.length
    ? [...gateChips, ...quickChips.slice(0, 2)]
    : quickChips;
  const entryBadge = entryMode === 'register'
    ? 'Creating account'
    : entryMode === 'login'
      ? 'Signing in'
      : entryMode === 'resume'
        ? 'Resuming'
        : entryMode === 'manual'
          ? 'Entry chosen by you'
          : '';
  const methodBadge = loginMethod ? String(loginMethod).replace(/_/g, ' ') : '';
  const identifierBadge = loginIdentifier ? String(loginIdentifier).replace(/_/g, ' ') : '';

  return (
    <div className="glass-panel rounded-2xl shadow-2xl flex flex-col h-full min-h-[460px] overflow-hidden">
      {/* Header */}
      <div className="p-3.5 bg-white/[0.02] border-b border-white/[0.08] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-700 flex items-center justify-center text-white font-black text-xs shadow-md shadow-indigo-500/20 border border-indigo-400/30">
              FP
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-400 rounded-full border border-[#07090e] animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-slate-100">Ask FormPilot</h3>
              <span className="text-[10px] font-semibold text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/30">
                Copilot
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Instant guidance, saved details, and stage actions
            </p>
            {(entryBadge || methodBadge || identifierBadge) && (
              <div className="mt-1 flex flex-wrap items-center gap-1">
                {entryBadge && (
                  <span className="rounded-full border border-sky-500/30 bg-sky-950/60 px-2 py-0.5 text-[9px] font-semibold text-sky-300">
                    {entryBadge}
                  </span>
                )}
                {methodBadge && (
                  <span className="rounded-full border border-emerald-500/30 bg-emerald-950/60 px-2 py-0.5 text-[9px] font-semibold text-emerald-300">
                    {methodBadge}
                  </span>
                )}
                {identifierBadge && (
                  <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[9px] font-semibold text-slate-300">
                    {identifierBadge}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={() => onClearChat?.()}
          className="p-1.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-colors"
          title="Clear conversation"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Messages Stream */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3.5 bg-transparent">
        {aiConfigured === false && (
          <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs text-indigo-200">
            The AI model is not configured yet. Add a model key in Settings → AI assistant to enable free-form reasoning and automated execution.
          </div>
        )}
        {messages.map((m, i) => {
          const isUser = m.sender === 'Candidate';
          return (
            <div
              key={`${m.time}-${i}-${m.sender}`}
              className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} animate-fadeIn`}
            >
              <div className="flex items-center gap-1.5 mb-1 text-[10px] text-slate-500">
                {isUser ? (
                  <>
                    <span className="text-indigo-300 font-semibold">You</span>
                    <Clock className="w-2.5 h-2.5" />
                    <span>{m.time}</span>
                  </>
                ) : (
                  <>
                    <span className="text-indigo-400 font-semibold">FormPilot</span>
                    <Clock className="w-2.5 h-2.5" />
                    <span>{m.time}</span>
                  </>
                )}
              </div>

              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs leading-relaxed transition-all ${
                  isUser
                    ? 'bg-gradient-to-br from-indigo-600 to-indigo-700 text-white font-medium rounded-tr-sm shadow-md shadow-indigo-600/20 border border-indigo-400/30'
                    : 'glass-panel-elevated text-slate-100 rounded-tl-sm shadow-lg'
                }`}
              >
                <div className="whitespace-pre-line">{m.text}</div>

                {m.action_taken === 'FIELD_UPDATED' && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Updated: {m.field_updated} → {m.new_value}</span>
                  </div>
                )}
                {m.action_taken === 'PAUSED' && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-amber-400 font-semibold">
                    <PauseCircle className="w-3 h-3 text-amber-400 shrink-0" />
                    <span>Application paused</span>
                  </div>
                )}
                {m.action_taken === 'RESUMED' && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 font-semibold">
                    <PlayCircle className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Application resumed</span>
                  </div>
                )}
                {m.action_taken === 'LIVE_SEARCH' && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-cyan-400 font-semibold">
                    <Search className="w-3 h-3 text-cyan-400 shrink-0" />
                    <span>Live web results</span>
                  </div>
                )}
                {['ENTRY_MODE_SELECTED', 'ENTRY_MODE_REQUESTED'].includes(m.action_taken) && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-sky-300 font-semibold">
                    <CheckCircle2 className="w-3 h-3 text-sky-300 shrink-0" />
                    <span>Entry path: {m.entry_mode || 'selected'}</span>
                  </div>
                )}
                {m.action_taken === 'LOGIN_METHOD_SELECTED' && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-emerald-300 font-semibold">
                    <CheckCircle2 className="w-3 h-3 text-emerald-300 shrink-0" />
                    <span>Sign-in method: {String(m.login_method || '').replace(/_/g, ' ')}</span>
                  </div>
                )}
                {m.action_taken === 'ACCOUNT_IDENTIFIER_SELECTED' && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-slate-300 font-semibold">
                    <CheckCircle2 className="w-3 h-3 text-slate-300 shrink-0" />
                    <span>Account identified by: {String(m.login_identifier || '').replace(/_/g, ' ')}</span>
                  </div>
                )}
                {['FILL_RECHECK', 'FILL_CONTINUE', 'FILL_INCOMPLETE'].includes(m.action_taken) && (
                  <div className="mt-2 pt-2 border-t border-white/[0.08] flex items-center gap-1.5 text-[11px] font-mono text-amber-300 font-semibold">
                    <AlertTriangle className="w-3 h-3 text-amber-300 shrink-0" />
                    <span>
                      {m.action_taken === 'FILL_RECHECK'
                        ? 'Rechecking every field'
                        : m.action_taken === 'FILL_CONTINUE'
                          ? 'Continuing with an incomplete fill recorded'
                          : 'Some fields are not filled'}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-indigo-400 animate-pulse py-1">
            <Sparkles className="w-3.5 h-3.5 animate-spin" />
            <span>FormPilot is reasoning…</span>
          </div>
        )}
      </div>

      {/* Suggested Prompt Chips */}
      <div className="px-3 py-2 bg-white/[0.02] border-t border-white/[0.08] flex items-center gap-1.5 overflow-x-auto no-scrollbar shrink-0">
        {chips.map((chip, idx) => (
          <button
            key={`${chip.label}-${idx}`}
            type="button"
            onClick={() => handleSend(chip.query)}
            className="whitespace-nowrap px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-indigo-500/15 text-slate-300 hover:text-indigo-200 text-xs font-medium border border-white/[0.08] hover:border-indigo-500/40 transition-all shrink-0 shadow-sm"
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Omnibox Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="p-3 bg-[#07090e]/80 border-t border-white/[0.08] flex items-center gap-2 shrink-0"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question or command an update…"
          className="flex-1 px-4 py-2.5 rounded-xl glass-input text-slate-100 placeholder-slate-500 text-xs font-medium outline-none"
        />

        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-400 hover:to-violet-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          <span>Send</span>
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
}
