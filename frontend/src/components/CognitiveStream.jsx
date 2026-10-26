import React, { useEffect, useRef, useState } from 'react';
import { Terminal, Activity, Eye, Brain, CheckCircle2, Zap, ArrowDown } from 'lucide-react';

export default function CognitiveStream({ events, voiceEnabled }) {
  const scrollRef = useRef(null);
  const [filter, setFilter] = useState('ALL');
  const lastSpokenRef = useRef('');

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  useEffect(() => {
    if (!voiceEnabled || events.length === 0) return;
    const latestEvent = events[events.length - 1];
    const textToSpeak = latestEvent.hindi;
    if (!textToSpeak || textToSpeak === lastSpokenRef.current || !('speechSynthesis' in window)) return;

    lastSpokenRef.current = textToSpeak;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(textToSpeak);
      utterance.lang = 'hi-IN';
      utterance.rate = 1.05;
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      console.error('Voice error:', err);
    }
  }, [events, voiceEnabled]);

  const filteredEvents =
    filter === 'ALL' ? events : events.filter((e) => e.phase === filter);

  const getPhaseBadge = (phase) => {
    switch (phase) {
      case 'SENSE':
        return {
          icon: <Eye className="w-3.5 h-3.5" />,
          label: 'CHECK',
          color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
        };
      case 'THINK':
        return {
          icon: <Brain className="w-3.5 h-3.5" />,
          label: 'PLAN',
          color: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
        };
      case 'DECIDE':
        return {
          icon: <CheckCircle2 className="w-3.5 h-3.5" />,
          label: 'REVIEW',
          color: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
        };
      case 'ACT':
        return {
          icon: <Zap className="w-3.5 h-3.5" />,
          label: 'ACTION',
          color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
        };
      default:
        return {
          icon: <Activity className="w-3.5 h-3.5" />,
          label: 'UPDATE',
          color: 'bg-slate-800 text-slate-300 border-slate-700',
        };
    }
  };

  const filterTabs = [
    { value: 'ALL', label: 'All' },
    { value: 'SENSE', label: 'Checks' },
    { value: 'THINK', label: 'Plan' },
    { value: 'DECIDE', label: 'Reviews' },
    { value: 'ACT', label: 'Actions' },
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl flex flex-col h-[520px] shadow-xl overflow-hidden">
      <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-amber-400" />
          <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            Application activity
          </h2>
          <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono">
            {events.length} updates
          </span>
        </div>

        <div className="flex items-center gap-1 bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-[10px] font-semibold">
          {filterTabs.map((p) => (
            <button
              key={p.value}
              onClick={() => setFilter(p.value)}
              className={`px-2 py-1 rounded transition-colors ${
                filter === p.value
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-xs">
        {filteredEvents.length === 0 ? (
          <div className="text-center py-16 text-slate-600">
            <Activity className="w-8 h-8 mx-auto mb-2 opacity-40 animate-pulse" />
            <p>Start an application to see each step here.</p>
          </div>
        ) : (
          filteredEvents.map((ev, index) => {
            const badge = getPhaseBadge(ev.phase);
            return (
              <div
                key={index}
                className="p-3 rounded-xl bg-slate-950/70 border border-slate-800/80 hover:border-slate-700 transition-colors"
              >
                <div className="flex items-center justify-between mb-1.5 font-sans">
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-extrabold border ${badge.color}`}>
                      {badge.icon}
                      <span>{badge.label}</span>
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">
                      {ev.timestamp}
                    </span>
                  </div>
                </div>

                <div className="text-slate-300 text-xs font-mono leading-relaxed pl-1">
                  {ev.message}
                </div>

                {ev.hindi && (
                  <div className="mt-2 pt-2 border-t border-slate-800/60 font-sans text-xs text-amber-300/90 flex items-start gap-1.5 pl-1 italic">
                    <span className="shrink-0 not-italic font-bold text-amber-400">Voice:</span>
                    <span>&ldquo;{ev.hindi}&rdquo;</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div className="bg-slate-950/90 px-4 py-2 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center justify-between font-sans">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          <span>Live updates</span>
        </span>
        <button
          onClick={() => {
            if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
          }}
          className="text-slate-400 hover:text-slate-200 flex items-center gap-1 text-[10px]"
        >
          <span>Jump to latest</span>
          <ArrowDown className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
