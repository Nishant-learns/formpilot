import React, { useEffect, useRef, useState } from 'react';
import {
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

export default function LiveChat({ onSendMessage, chatMessages, voiceEnabled, onClearChat }) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const lastSpokenRef = useRef(WELCOME.text);

  const messages = chatMessages?.length ? chatMessages : [WELCOME];

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

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl flex flex-col h-full min-h-[460px] overflow-hidden">
      <div className="p-3.5 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-amber-600 to-orange-500 flex items-center justify-center text-slate-950 font-black text-xs shadow-md">
              FP
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-500 rounded-full border border-slate-900 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="text-xs font-bold text-slate-200">Ask FormPilot</h3>
              <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-950/60 px-1.5 py-0.2 rounded border border-emerald-500/30">
                Here to help
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Questions, saved details, or a quick progress check
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => onClearChat?.()}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          title="Clear conversation"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3.5 bg-slate-950/40">
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
                    <span>You</span>
                    <Clock className="w-2.5 h-2.5" />
                    <span>{m.time}</span>
                  </>
                ) : (
                  <>
                    <span className="text-amber-400 font-semibold">FormPilot</span>
                    <Clock className="w-2.5 h-2.5" />
                    <span>{m.time}</span>
                  </>
                )}
              </div>

              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs leading-relaxed ${
                  isUser
                    ? 'bg-gradient-to-r from-amber-600 via-orange-600 to-amber-500 text-slate-950 font-medium rounded-tr-none shadow-md'
                    : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none shadow-lg'
                }`}
              >
                <div className="whitespace-pre-line">{m.text}</div>

                {m.action_taken === 'FIELD_UPDATED' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Updated: {m.field_updated} → {m.new_value}</span>
                  </div>
                )}
                {m.action_taken === 'PAUSED' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-amber-400 font-semibold">
                    <PauseCircle className="w-3 h-3 text-amber-400 shrink-0" />
                    <span>Application paused</span>
                  </div>
                )}
                {m.action_taken === 'RESUMED' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 font-semibold">
                    <PlayCircle className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Application resumed</span>
                  </div>
                )}
                {m.action_taken === 'LIVE_SEARCH' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-cyan-400 font-semibold">
                    <Search className="w-3 h-3 text-cyan-400 shrink-0" />
                    <span>Live web results</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-amber-400 animate-pulse py-1">
            <Sparkles className="w-3.5 h-3.5" />
            <span>FormPilot is checking…</span>
          </div>
        )}
      </div>

      <div className="px-3 py-2 bg-slate-950/60 border-t border-slate-800/60 flex items-center gap-1.5 overflow-x-auto no-scrollbar shrink-0">
        {quickChips.map((chip, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => handleSend(chip.query)}
            className="whitespace-nowrap px-2.5 py-1 rounded-lg bg-slate-800/70 hover:bg-slate-800 text-slate-300 hover:text-amber-300 text-[11px] font-medium border border-slate-700/60 transition-all shrink-0"
          >
            {chip.label}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2 shrink-0"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question or request a change…"
          className="flex-1 px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 focus:border-amber-500 focus:ring-1 focus:ring-amber-500/40 text-slate-100 placeholder-slate-500 text-xs font-medium outline-none transition-all"
        />

        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 shadow-md shadow-amber-500/10 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          <span>Send</span>
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
}
