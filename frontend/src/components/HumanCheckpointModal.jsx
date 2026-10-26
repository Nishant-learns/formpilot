import React, { useState } from 'react';
import {
  ShieldAlert,
  Key,
  HelpCircle,
  CheckCircle2,
  Lock,
  AlertOctagon,
  FileCheck2,
  ArrowRight,
  Sparkles,
  Smartphone,
  BellRing,
  ExternalLink,
  X,
  Download,
} from 'lucide-react';

export default function HumanCheckpointModal(props) {
  if (!props.activeGate) return null;
  return <CheckpointContent {...props} />;
}

function statusLabel(status) {
  if (status === 'MATCH') return 'Matches';
  if (status === 'EMPTY') return 'Empty on form';
  if (status === 'MISMATCH') return 'Check this';
  return status || 'Checked';
}

function statusClass(status) {
  if (status === 'MATCH') return 'text-emerald-400';
  if (status === 'EMPTY' || status === 'MISMATCH') return 'text-amber-400';
  return 'text-slate-300';
}

function CheckpointContent({ activeGate, onSubmitResponse, onClose }) {
  const [inputVal, setInputVal] = useState('');
  const [captchaVal, setCaptchaVal] = useState('');
  const [otpVal, setOtpVal] = useState('');

  const handleGatewayChoice = (opt) => {
    onSubmitResponse({
      action: 'GATEWAY_CHOICE',
      id: opt.id,
      text: opt.text,
      type: opt.type,
    });
  };

  const handleMissingFieldSubmit = (e) => {
    e.preventDefault();
    if (!inputVal.trim()) return;
    onSubmitResponse({
      action: 'MISSING_FIELD_SUBMIT',
      key: activeGate.field_key,
      value: inputVal.trim(),
    });
    setInputVal('');
  };

  const handleCaptchaSubmit = (e) => {
    e.preventDefault();
    if (!captchaVal.trim()) return;
    onSubmitResponse({ action: 'CAPTCHA_SUBMIT', code: captchaVal.trim() });
    setCaptchaVal('');
  };

  const handleOtpSubmit = (e) => {
    e.preventDefault();
    if (!otpVal.trim()) return;
    onSubmitResponse({
      action: 'OTP_SUBMIT',
      otp: otpVal.trim(),
      code: otpVal.trim(),
    });
    setOtpVal('');
  };

  const handleSectionApproval = (approved) => {
    onSubmitResponse({ action: 'SECTION_APPROVAL', approved });
  };

  const dismiss = () => {
    if (onClose) onClose();
    fetch('/api/agent/dismiss-gate', { method: 'POST' }).catch(() => {});
  };

  const demoOtp = activeGate.demo_otp || (activeGate.description?.match(/\b(\d{6})\b/)?.[1] ?? '');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-fadeIn">
      <div className="bg-slate-900 border-2 border-amber-500/60 rounded-3xl max-w-2xl w-full shadow-2xl shadow-amber-500/10 overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-amber-600/30 via-orange-600/20 to-slate-900 px-6 py-4 border-b border-amber-500/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400">
              {activeGate.gate_type === 'GATEWAY_DECISION' && <Key className="w-5 h-5" />}
              {activeGate.gate_type === 'MISSING_FIELD' && <HelpCircle className="w-5 h-5" />}
              {activeGate.gate_type === 'CAPTCHA_SOLVE' && <Lock className="w-5 h-5" />}
              {activeGate.gate_type === 'OTP_RELAY' && <Smartphone className="w-5 h-5" />}
              {activeGate.gate_type === 'SECTION_APPROVAL' && <FileCheck2 className="w-5 h-5" />}
              {activeGate.gate_type === 'PRE_PAYMENT_SAFETY_LOCK' && <AlertOctagon className="w-6 h-6 text-red-400" />}
              {activeGate.gate_type === 'ERROR_DIAGNOSIS' && <ShieldAlert className="w-5 h-5 text-red-400" />}
            </div>
            <div>
              <h3 className="text-base font-extrabold text-white">{activeGate.title}</h3>
              <p className="text-xs text-amber-300">
                {activeGate.hindi_title || 'Please review this step'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 uppercase tracking-wider">
              Your review
            </span>
            <button
              type="button"
              onClick={dismiss}
              className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Close this review"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="p-6">
          {/* Gateway choice */}
          {activeGate.gate_type === 'GATEWAY_DECISION' && (
            <div>
              <p className="text-sm text-slate-300 mb-4 leading-relaxed">{activeGate.description}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {activeGate.options?.map((opt, i) => (
                  <button
                    key={i}
                    onClick={() => handleGatewayChoice(opt)}
                    className="p-5 rounded-2xl bg-slate-950/80 hover:bg-slate-800/80 border-2 border-slate-700 hover:border-amber-500/80 text-left transition-all group flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-amber-400 uppercase tracking-wider">
                          Option {i + 1}
                        </span>
                        <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 group-hover:translate-x-1 transition-all" />
                      </div>
                      <h4 className="text-base font-bold text-white mt-1 group-hover:text-amber-300">
                        {opt.text}
                      </h4>
                      <p className="text-xs text-slate-400 mt-1">
                        {opt.type === 'NEW_REGISTRATION'
                          ? 'Create a new application'
                          : 'Sign in to an existing account'}
                      </p>
                    </div>
                    <span className="mt-4 inline-block text-[11px] font-semibold text-slate-300 bg-slate-800 px-2.5 py-1 rounded-md border border-slate-700">
                      Choose this option
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Missing field */}
          {activeGate.gate_type === 'MISSING_FIELD' && (
            <form onSubmit={handleMissingFieldSubmit} className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <p className="text-xs text-slate-400 leading-relaxed">
                  This form asks for a detail that isn't saved yet. Enter it once and FormPilot
                  will remember it for future applications.
                </p>
                <div className="mt-3">
                  <label className="text-xs font-bold text-amber-300 block mb-1 uppercase tracking-wider">
                    {activeGate.field_label}
                  </label>
                  <input
                    type={activeGate.input_type || 'text'}
                    value={inputVal}
                    onChange={(e) => setInputVal(e.target.value)}
                    autoFocus
                    placeholder={`Enter ${activeGate.field_label}`}
                    className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:border-amber-500 focus:ring-1 focus:ring-amber-500 text-white font-medium text-sm outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="submit"
                  disabled={!inputVal.trim()}
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg disabled:opacity-50"
                >
                  <Sparkles className="w-4 h-4" />
                  <span>Save and fill this field</span>
                </button>
              </div>
            </form>
          )}

          {/* CAPTCHA */}
          {activeGate.gate_type === 'CAPTCHA_SOLVE' && (
            <form onSubmit={handleCaptchaSubmit} className="space-y-4">
              <p className="text-xs text-slate-300">{activeGate.description}</p>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col md:flex-row items-center gap-5 justify-center">
                {activeGate.captcha_image ? (
                  <div className="p-2 rounded-lg bg-slate-900 border border-slate-700 shadow-inner">
                    <img
                      src={activeGate.captcha_image}
                      alt="Security check characters"
                      className="max-h-20 object-contain rounded"
                    />
                  </div>
                ) : (
                  <div className="text-xs text-slate-500">
                    The security check is shown in the live portal view.
                  </div>
                )}

                <div className="flex-1 w-full max-w-xs">
                  <input
                    type="text"
                    value={captchaVal}
                    onChange={(e) => setCaptchaVal(e.target.value)}
                    autoFocus
                    placeholder="Enter the characters"
                    className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:border-amber-500 text-center text-lg font-mono font-bold tracking-widest text-amber-300 outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="submit"
                  disabled={!captchaVal.trim()}
                  className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 disabled:opacity-50"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Submit and continue</span>
                </button>
              </div>
            </form>
          )}

          {/* OTP */}
          {activeGate.gate_type === 'OTP_RELAY' && (
            <form onSubmit={handleOtpSubmit} className="space-y-4">
              <div className="p-4 rounded-xl bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-950 border border-emerald-500/40 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
                    </span>
                    <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
                      Verification code sent
                    </span>
                  </div>
                  {activeGate.recipient && (
                    <span className="text-[10px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                      To: {activeGate.recipient}
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-300">
                  {activeGate.description || 'Enter the 6-digit code sent to the phone number saved in your details.'}
                </p>

                {activeGate.ntfy_url && (
                  <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <BellRing className="w-4 h-4 text-emerald-400" />
                      <div>
                        <div className="text-xs font-semibold text-slate-200">Phone alert channel</div>
                        <div className="text-[11px] font-mono text-emerald-400">
                          {activeGate.ntfy_url}
                        </div>
                      </div>
                    </div>
                    <a
                      href={activeGate.ntfy_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-xs font-bold flex items-center gap-1.5 transition-colors"
                    >
                      <span>Open alerts</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}

                <div className="text-[11px] text-slate-400 flex items-center justify-between gap-3">
                  <span>FormPilot never stores this code.</span>
                  {demoOtp && (
                    <button
                      type="button"
                      onClick={() => setOtpVal(demoOtp)}
                      className="text-amber-400 font-mono font-bold bg-amber-500/10 hover:bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/30 text-xs transition-colors"
                    >
                      Use demo code: {demoOtp}
                    </button>
                  )}
                </div>
              </div>

              <div className="flex flex-col items-center gap-3 pt-1">
                <input
                  type="text"
                  maxLength={6}
                  value={otpVal}
                  onChange={(e) => setOtpVal(e.target.value)}
                  autoFocus
                  placeholder="Enter 6-digit code"
                  className="w-64 px-4 py-3 rounded-xl bg-slate-950 border-2 border-emerald-500/60 focus:border-emerald-400 text-center text-2xl font-mono font-extrabold tracking-widest text-emerald-300 outline-none shadow-lg shadow-emerald-500/10"
                />
              </div>

              <div className="flex items-center justify-between gap-3 pt-2">
                <button
                  type="button"
                  onClick={dismiss}
                  className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs transition-colors"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={!otpVal.trim()}
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg shadow-emerald-500/20 disabled:opacity-50"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Verify and continue</span>
                </button>
              </div>
            </form>
          )}

          {/* Section review */}
          {activeGate.gate_type === 'SECTION_APPROVAL' && (
            <div className="space-y-4">
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 font-medium">
                Section {activeGate.section_number} is ready. Please check these details against the
                form before continuing.
              </div>

              {activeGate.fields_filled && activeGate.fields_filled.length > 0 && (
                <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="pb-2">Field</th>
                        <th className="pb-2">Filled value</th>
                        <th className="pb-2 text-right">Check</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {activeGate.fields_filled.map((f, i) => (
                        <tr key={i} className="hover:bg-slate-900/50">
                          <td className="py-1.5 text-slate-300">{f.field_label}</td>
                          <td className="py-1.5 text-amber-300 font-semibold">{f.injected_value}</td>
                          <td className="py-1.5 text-right text-emerald-400 font-sans text-[11px]">
                            Filled
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => handleSectionApproval(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  I need to edit something
                </button>
                <button
                  type="button"
                  onClick={() => handleSectionApproval(true)}
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Confirm and continue</span>
                </button>
              </div>
            </div>
          )}

          {/* Safety handover: payment or final submission */}
          {activeGate.gate_type === 'PRE_PAYMENT_SAFETY_LOCK' && (
            <div className="space-y-4">
              <div className="p-4 rounded-2xl bg-red-500/10 border-2 border-red-500/50 text-red-200">
                <div className="flex items-center gap-2 text-sm font-extrabold text-red-400 uppercase tracking-wide">
                  <ShieldAlert className="w-5 h-5" />
                  <span>{activeGate.final_action === 'submission' ? 'Nothing submitted' : 'Payment not started'}</span>
                </div>
                <p className="text-xs text-red-300/90 mt-2 leading-relaxed">
                  {activeGate.description}
                </p>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                    Details check before you continue
                  </span>
                  <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-mono">
                    {activeGate.total_verified_fields} of {activeGate.total_checked_fields || activeGate.total_verified_fields} checked
                  </span>
                </div>
                <div className="max-h-56 overflow-y-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="pb-2">Field</th>
                        <th className="pb-2">Saved value</th>
                        <th className="pb-2 text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {activeGate.audit_diff?.map((r, i) => (
                        <tr key={i}>
                          <td className="py-1.5 text-slate-300">{r.field}</td>
                          <td className="py-1.5 text-amber-300 font-semibold">{r.vault_value}</td>
                          <td className={`py-1.5 text-right font-bold ${statusClass(r.status)}`}>
                            {statusLabel(r.status)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300">
                <strong>Next step:</strong>{' '}
                {activeGate.final_action === 'submission'
                  ? 'complete the final submission yourself on the official portal.'
                  : 'complete the payment yourself on the official portal.'}{' '}
                FormPilot will not click the payment or submit button.
              </div>

              <div className="flex items-center justify-between gap-3 pt-2">
                {activeGate.run_id && (
                  <a
                    href={`/api/runs/${activeGate.run_id}/audit`}
                    className="px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-semibold border border-slate-700 flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download details</span>
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => onSubmitResponse({ action: 'ACKNOWLEDGE_LOCK' })}
                  className="px-6 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold border border-slate-700"
                >
                  Understood
                </button>
              </div>
            </div>
          )}

          {/* Portal error */}
          {activeGate.gate_type === 'ERROR_DIAGNOSIS' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-300">
                <span className="font-bold block mb-1">The portal showed this message:</span>
                <span className="font-mono">{activeGate.error_text}</span>
              </div>

              <div className="space-y-2">
                <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                  How would you like to continue?
                </span>
                <div className="grid grid-cols-1 gap-2">
                  {activeGate.suggested_actions?.map((act, i) => (
                    <button
                      key={i}
                      onClick={() => onSubmitResponse({ action: 'ERROR_RECOVERY', choice: act })}
                      className="p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 text-left text-xs text-slate-200 font-medium transition-all flex items-center justify-between"
                    >
                      <span>{act}</span>
                      <ArrowRight className="w-3.5 h-3.5 text-amber-400" />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Fallback */}
          {!['GATEWAY_DECISION', 'MISSING_FIELD', 'CAPTCHA_SOLVE', 'OTP_RELAY', 'SECTION_APPROVAL', 'PRE_PAYMENT_SAFETY_LOCK', 'ERROR_DIAGNOSIS'].includes(activeGate.gate_type) && (
            <div className="space-y-4 text-center py-4">
              <p className="text-sm text-slate-300">
                {activeGate.description || 'FormPilot is waiting for your confirmation to continue.'}
              </p>
              <div className="flex justify-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => onSubmitResponse({ action: 'CONTINUE' })}
                  className="px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm"
                >
                  Continue
                </button>
                <button
                  type="button"
                  onClick={dismiss}
                  className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm"
                >
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
