import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  Bot, 
  User, 
  Sparkles, 
  CheckCircle2, 
  Trash2, 
  HelpCircle, 
  Edit3, 
  PauseCircle, 
  PlayCircle, 
  Search, 
  FileText,
  Clock,
  ArrowRight
} from 'lucide-react';

export default function LiveChat({ onSendMessage, chatMessages, voiceEnabled }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState(chatMessages || [
    {
      sender: 'CyberBhaiya',
      text: "Namaste! Mai hoon Cyber Bhaiya (FormPilot). Form bharte waqt koi bhi doubt ho, kisi field ko badalna ho (jaise 'father name change karo'), ya status check karna ho, yahan mujhse bejhijhak baat karein!",
      time: 'Now',
      action_taken: 'GREETING'
    }
  ]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

  // Sync external chatMessages if updated
  useEffect(() => {
    if (chatMessages && chatMessages.length > 0) {
      setMessages(chatMessages);
    }
  }, [chatMessages]);

  // Auto-scroll on new message
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const quickChips = [
    { label: '💰 Fees kitni hai?', query: 'Bhaiya is form ki fees kitni hai?' },
    { label: '✏️ DOB update karo', query: 'DOB change karke 15/08/2004 karo' },
    { label: '📄 Documents checklist', query: 'Kaun kaun se documents upload karne honge?' },
    { label: '📸 Photo specs kya hai?', query: 'Photograph aur signature ka specification batao' },
    { label: '⏸️ Form pause karo', query: 'Bhaiya thoda pause karo' },
    { label: '🚀 Status report', query: 'Abhi tak kaunse fields fill hue hain status batao' }
  ];

  const handleSend = async (textToSend) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    const userTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg = { sender: 'Candidate', text: text, time: userTime };
    
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      if (onSendMessage) {
        await onSendMessage(text);
      } else {
        const res = await fetch('/api/chat/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        if (res.ok) {
          const data = await res.json();
          const bhaiyaMsg = {
            sender: 'CyberBhaiya',
            text: data.reply,
            time: data.timestamp || userTime,
            action_taken: data.action_taken,
            field_updated: data.field_updated,
            new_value: data.new_value
          };
          setMessages((prev) => [...prev, bhaiyaMsg]);

          // Speech synthesis if voiceEnabled
          if (voiceEnabled && 'speechSynthesis' in window) {
            try {
              window.speechSynthesis.cancel();
              const utterance = new SpeechSynthesisUtterance(data.reply);
              utterance.lang = 'hi-IN';
              utterance.rate = 1.05;
              window.speechSynthesis.speak(utterance);
            } catch (err) {}
          }
        }
      }
    } catch (err) {
      console.error('Chat send error:', err);
      setMessages((prev) => [
        ...prev,
        {
          sender: 'CyberBhaiya',
          text: "Chinta mat karein, network glitch tha. Kripya dobara poochiye!",
          time: userTime
        }
      ]);
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

  const clearChat = () => {
    setMessages([
      {
        sender: 'CyberBhaiya',
        text: "Chat refresh ho gayi hai. Batayein ab kya madad chahiye?",
        time: 'Now'
      }
    ]);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl flex flex-col h-[520px] overflow-hidden">
      
      {/* Top Chat Header */}
      <div className="p-3.5 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-amber-600 to-orange-500 flex items-center justify-center text-slate-950 font-black text-xs shadow-md">
              CB
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-500 rounded-full border border-slate-900 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="text-xs font-bold text-slate-200">
                Chat with AI Cyber Bhaiya
              </h3>
              <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-950/60 px-1.5 py-0.2 rounded border border-emerald-500/30">
                Live Companion
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Ask questions • Live field edits • Pause/Resume workflow
            </p>
          </div>
        </div>

        <button
          onClick={clearChat}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          title="Clear Conversation"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Messages Scroll Area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3.5 bg-slate-950/40">
        {messages.map((m, i) => {
          const isUser = m.sender === 'Candidate';
          return (
            <div
              key={i}
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
                    <span className="text-amber-400 font-semibold">CyberBhaiya</span>
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

                {/* Action Badges */}
                {m.action_taken === 'FIELD_UPDATED' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Updated in Live DOM: {m.field_updated} → {m.new_value}</span>
                  </div>
                )}
                {m.action_taken === 'PAUSED' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-amber-400 font-semibold">
                    <PauseCircle className="w-3 h-3 text-amber-400 shrink-0" />
                    <span>Browser Execution Paused</span>
                  </div>
                )}
                {m.action_taken === 'RESUMED' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 font-semibold">
                    <PlayCircle className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Navigation Resumed</span>
                  </div>
                )}
                {m.action_taken === 'TINYFISH_SEARCH' && (
                  <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center gap-1.5 text-[11px] font-mono text-cyan-400 font-semibold">
                    <Search className="w-3 h-3 text-cyan-400 shrink-0" />
                    <span>Live Search via TinyFish Oracle (IN)</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-amber-400 animate-pulse py-1">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Cyber Bhaiya soch rahe hain aur verify kar rahe hain...</span>
          </div>
        )}
      </div>

      {/* Quick Suggestion Chips */}
      <div className="px-3 py-2 bg-slate-950/60 border-t border-slate-800/60 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
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

      {/* Input Form */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Bhaiya a question or say 'father name badlo to...'"
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
