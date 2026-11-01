import React, { useEffect, useRef, useState } from 'react';
import { Terminal, Activity, Eye, Brain, CheckCircle2, Zap, ArrowDown } from 'lucide-react';
import { AudioWaveformIcon, NeuralSparkleIcon } from './CustomIcons';

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
          color: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
        };
      case 'THINK':
        return {
          icon: <Brain className="w-3.5 h-3.5" />,
          label: 'PLAN',
          color: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
        };
      case 'DECIDE':
        return {
          icon: <CheckCircle2 className="w-3.5 h-3.5" />,
          label: 'REVIEW',
          color: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
        };
      case 'ACT':
        return {
          icon: <Zap className="w-3.5 h-3.5" />,
          label: 'ACTION',
          color: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
        };
      default:
        return {
          icon: <Activity className="w-3.5 h-3.5" />,
          label: 'UPDATE',
          color: 'bg-white/[0.05] text-slate-300 border-white/[0.08]',
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
    <div className="glass-panel rounded-2xl flex flex-col h-full min-h-[460px] shadow-2xl overflow-hidden">
      {/* Header */}
      <div className="bg-white/[0.02] px-4 py-3 border-b border-white/[0.08] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <NeuralSparkleIcon className="w-4 h-4 text-indigo-400" />
          <h2 className="text-xs font-bold text-slate-200 tracking-wide uppercase">
            Cognitive Stream
          </h2>
          <span className="text-[10px] bg-white/[0.06] text-slate-400 px-2 py-0.5 rounded-full font-mono border border-white/[0.08]">
            {events.length} nodes
          </span>
        </div>

        <div className="flex items-center gap-1 bg-black/40 p-1 rounded-xl border border-white/[0.08] text-[10px] font-semibold">
          {filterTabs.map((p) => (
            <button
              key={p.value}
              onClick={() => setFilter(p.value)}
              className={`px-2.5 py-1 rounded-lg transition-all ${
                filter === p.value
                  ? 'bg-indigo-500/20 text-indigo-200 border border-indigo-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Events timeline */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-xs">
        {filteredEvents.length === 0 ? (
          <div className="text-center py-20 text-slate-600">
            <Activity className="w-8 h-8 mx-auto mb-2 opacity-30 animate-pulse text-indigo-400" />
            <p className="text-xs text-slate-500">Autonomous reasoning decisions will stream in real time.</p>
          </div>
        ) : (
          filteredEvents.map((ev, index) => {
            const badge = getPhaseBadge(ev.phase);
            return (
              <div
                key={index}
                className="animate-fadeIn p-3.5 rounded-xl glass-panel-elevated hover:border-white/[0.18] transition-all shadow-sm relative group"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold border ${badge.color}`}>
                      {badge.icon}
                      <span>{badge.label}</span>
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {ev.timestamp}
                    </span>
                  </div>
                </div>

                <div className="text-slate-200 text-xs font-sans leading-relaxed">
                  {ev.message}
                </div>

                {ev.hindi && (
                  <div className="mt-2.5 pt-2 border-t border-white/[0.06] text-xs text-indigo-200 flex items-start gap-2 bg-indigo-500/10 -mx-1 px-3 py-2 rounded-xl border border-indigo-500/20">
                    <AudioWaveformIcon active={voiceEnabled} className="h-3.5 w-3.5 shrink-0 text-indigo-300 mt-0.5" />
                    <span className="leading-snug italic">&ldquo;{ev.hindi}&rdquo;</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Bottom Telemetry Bar */}
      <div className="bg-white/[0.02] px-4 py-2 border-t border-white/[0.08] text-[11px] text-slate-400 flex items-center justify-between font-sans">
        <span className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-mono text-[10px] text-slate-400">Decision Pipeline Live</span>
        </span>
        <button
          onClick={() => {
            if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
          }}
          className="text-slate-400 hover:text-white flex items-center gap-1 text-[11px] font-medium transition-colors"
        >
          <span>Scroll to head</span>
          <ArrowDown className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
