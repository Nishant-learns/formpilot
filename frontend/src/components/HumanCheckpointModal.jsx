import React, { useEffect, useRef, useState } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  BellRing,
  Camera,
  CheckCircle2,
  Download,
  ExternalLink,
  FileCheck2,
  FileUp,
  HelpCircle,
  Image as ImageIcon,
  Key,
  Loader2,
  Lock,
  MousePointer2,
  RefreshCw,
  ShieldAlert,
  Smartphone,
  Sparkles,
  Upload,
  X,
} from 'lucide-react';

const LIVE_GATES = new Set(['LIVE_HANDOFF', 'LIVE_PHOTO', 'FILE_UPLOAD', 'UNKNOWN_FIELD']);

export default function HumanCheckpointModal(props) {
  if (!props.activeGate || props.hidden) return null;
  const key = [
    props.activeGate.gate_type,
    props.activeGate.field_key || '',
    props.activeGate.section_number || '',
  ].join(':');
  return <CheckpointContent key={key} {...props} />;
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

function entryOptionDescription(option) {
  const mode = option.mode || option.type;
  if (mode === 'register') return 'Create a new account and start a fresh application';
  if (mode === 'login') return 'Sign in to an existing account';
  if (mode === 'resume') return 'Resume an application you already started';
  if (mode === 'manual' || option.source === 'current_page') {
    return 'Continue on the page that is already open';
  }
  return 'Use this entry path';
}

function GateIcon({ type }) {
  if (type === 'GATEWAY_DECISION') return <Key className="w-5 h-5" />;
  if (type === 'LOGIN_METHOD' || type === 'ACCOUNT_IDENTIFIER') return <Key className="w-5 h-5" />;
  if (type === 'FILL_INCOMPLETE') return <AlertTriangle className="w-5 h-5 text-amber-400" />;
  if (type === 'MISSING_FIELD' || type === 'UNKNOWN_FIELD') return <HelpCircle className="w-5 h-5" />;
  if (type === 'CAPTCHA_SOLVE' || type === 'LIVE_HANDOFF') return <Lock className="w-5 h-5" />;
  if (type === 'OTP_RELAY') return <Smartphone className="w-5 h-5" />;
  if (type === 'SECTION_APPROVAL') return <FileCheck2 className="w-5 h-5" />;
  if (type === 'LIVE_PHOTO') return <Camera className="w-5 h-5" />;
  if (type === 'FILE_UPLOAD') return <FileUp className="w-5 h-5" />;
  if (type === 'PRE_PAYMENT_SAFETY_LOCK') return <AlertOctagon className="w-6 h-6 text-red-400" />;
  if (type === 'ERROR_DIAGNOSIS') return <ShieldAlert className="w-5 h-5 text-red-400" />;
  return <ShieldAlert className="w-5 h-5" />;
}

function CheckpointContent({ activeGate, onSubmitResponse, onClose, onDismissGate, liveSession }) {
  const [inputVal, setInputVal] = useState('');
  const [captchaVal, setCaptchaVal] = useState('');
  const [otpVal, setOtpVal] = useState('');
  const [editingSection, setEditingSection] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState('');
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState('');

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const previewRef = useRef('');
  const fileInputRef = useRef(null);

  const hasLive = Boolean(activeGate.live_session || liveSession);
  const docked = hasLive && activeGate.gate_type !== 'GATEWAY_DECISION';
  const isUploadGate = activeGate.gate_type === 'LIVE_PHOTO' || activeGate.gate_type === 'FILE_UPLOAD';

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraActive(false);
  };

  useEffect(() => {
    if (!cameraActive || !streamRef.current || !videoRef.current) return;
    videoRef.current.srcObject = streamRef.current;
    videoRef.current.play().catch(() => {});
  }, [cameraActive]);

  useEffect(() => () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
  }, []);

  const setPreviewFile = (file) => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const url = URL.createObjectURL(file);
    previewRef.current = url;
    setPhotoFile(file);
    setPhotoPreview(url);
    setUploadError('');
  };

  const chooseFile = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setUploadError('The file must be 5 MB or smaller.');
      return;
    }
    setPreviewFile(file);
  };

  const startCamera = async () => {
    setCameraError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('This browser cannot open the camera. Choose a photo file instead.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      setCameraActive(true);
    } catch (err) {
      setCameraError(
        'The camera was not available. Allow camera access and try again, or choose a recent photo.'
      );
    }
  };

  const capturePhoto = async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setCameraError('The camera is still starting. Wait a moment and try again.');
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
    if (!blob) {
      setCameraError('The photo could not be captured. Try again or choose a file.');
      return;
    }
    const file = new File([blob], `live-photo-${Date.now()}.jpg`, { type: 'image/jpeg' });
    setPreviewFile(file);
    stopCamera();
  };

  const handleGatewayChoice = (option) => {
    onSubmitResponse({
      action: 'GATEWAY_CHOICE',
      id: option.id,
      element_id: option.element_id,
      text: option.text,
      type: option.type,
      mode: option.mode || option.type,
    });
  };

  const handleLoginMethodChoice = (option) => {
    onSubmitResponse({
      action: 'LOGIN_METHOD_CHOICE',
      method: option.method,
      value: option.value,
      text: option.text,
    });
  };

  const handleIdentifierChoice = (option) => {
    onSubmitResponse({
      action: 'ACCOUNT_IDENTIFIER_CHOICE',
      key: option.key,
      value: option.key,
      text: option.text,
    });
  };

  const handleMissingFieldSubmit = (event) => {
    event.preventDefault();
    if (!inputVal.trim()) return;
    onSubmitResponse({
      action: 'MISSING_FIELD_SUBMIT',
      key: activeGate.field_key,
      value: inputVal.trim(),
    });
    setInputVal('');
  };

  const handleUnknownFieldSubmit = (event) => {
    event.preventDefault();
    if (!inputVal.trim()) return;
    onSubmitResponse({
      action: 'UNKNOWN_FIELD_SUBMIT',
      key: activeGate.field_key,
      value: inputVal.trim(),
    });
    setInputVal('');
  };

  const handleCaptchaSubmit = (event) => {
    event.preventDefault();
    if (!captchaVal.trim()) return;
    onSubmitResponse({ action: 'CAPTCHA_SUBMIT', code: captchaVal.trim() });
    setCaptchaVal('');
  };

  const handleOtpSubmit = (event) => {
    event.preventDefault();
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

  const submitUpload = async () => {
    if (!photoFile || uploading) return;
    setUploading(true);
    setUploadError('');
    try {
      const form = new FormData();
      form.append('field_key', activeGate.field_key || 'photo_upload');
      form.append('file', photoFile, photoFile.name || 'upload.jpg');
      const response = await fetch('/api/agent/upload', { method: 'POST', body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'The portal did not accept the file.');
      }
      onSubmitResponse({
        action: 'UPLOAD_COMPLETE',
        field_key: activeGate.field_key,
      });
    } catch (err) {
      setUploadError(err.message || 'The upload failed. Try again or attach the file in the live browser.');
    } finally {
      setUploading(false);
    }
  };

  const dismissGate = () => {
    if (onDismissGate) {
      onDismissGate();
      return;
    }
    if (onClose) onClose();
    fetch('/api/agent/dismiss-gate', { method: 'POST' }).catch(() => {});
  };

  const hidePanel = () => {
    if (onClose) onClose();
  };

  const demoOtp = activeGate.demo_otp || (activeGate.description?.match(/\b(\d{6})\b/)?.[1] ?? '');
  const instructions = Array.isArray(activeGate.instructions) ? activeGate.instructions : [];

  return (
    <div
      className={
        docked
          ? 'fixed inset-x-0 bottom-0 z-50 p-3 sm:inset-auto sm:right-4 sm:bottom-4 sm:w-[440px] sm:p-0'
          : 'fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-fadeIn'
      }
    >
      <div
        className={`bg-slate-900 border-2 rounded-3xl w-full shadow-2xl overflow-hidden ${
          docked
            ? 'border-sky-500/50 max-h-[82vh] shadow-sky-950/40'
            : 'border-amber-500/60 max-w-2xl shadow-amber-500/10'
        }`}
      >
        {/* Header */}
        <div
          className={`px-5 py-3.5 border-b flex items-center justify-between ${
            docked
              ? 'bg-gradient-to-r from-sky-600/25 via-slate-900 to-slate-900 border-sky-500/30'
              : 'bg-gradient-to-r from-amber-600/30 via-orange-600/20 to-slate-900 border-amber-500/30'
          }`}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-slate-950/60 border border-sky-500/30 flex items-center justify-center text-sky-300 shrink-0">
              <GateIcon type={activeGate.gate_type} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-extrabold text-white truncate">{activeGate.title}</h3>
              <p className="text-[11px] text-sky-300/90 truncate">
                {activeGate.hindi_title || 'Please review this step'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 uppercase tracking-wider">
              {hasLive ? 'Live checkpoint' : 'Your review'}
            </span>
            <button
              type="button"
              onClick={hidePanel}
              className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title={hasLive ? 'Hide this panel. The live browser stays available.' : 'Hide this review'}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="p-5 max-h-[72vh] overflow-y-auto">
          {hasLive && activeGate.gate_type !== 'PRE_PAYMENT_SAFETY_LOCK' && (
            <div className="mb-4 flex items-start gap-2 rounded-xl bg-sky-500/10 border border-sky-500/30 px-3 py-2 text-[11px] text-sky-200">
              <MousePointer2 className="w-4 h-4 text-sky-300 shrink-0 mt-0.5" />
              <span>
                This panel is docked so you can use the live browser at the same time. Click and
                type directly on the portal; FormPilot stays paused until you continue here.
              </span>
            </div>
          )}

          {/* Gateway choice */}
          {activeGate.gate_type === 'GATEWAY_DECISION' && (
            <div>
              <p className="text-sm text-slate-300 mb-4 leading-relaxed">{activeGate.description}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {activeGate.options?.map((option, index) => (
                  <button
                    key={option.element_id || option.id || index}
                    type="button"
                    onClick={() => handleGatewayChoice(option)}
                    className="p-4 rounded-2xl bg-slate-950/80 hover:bg-slate-800/80 border-2 border-slate-700 hover:border-amber-500/80 text-left transition-all group flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono text-amber-400 uppercase tracking-wider">
                          Option {index + 1}
                        </span>
                        <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 group-hover:translate-x-1 transition-all" />
                      </div>
                      <h4 className="text-sm font-bold text-white mt-1 group-hover:text-amber-300">
                        {option.text}
                      </h4>
                      <p className="text-[11px] text-slate-400 mt-1">
                        {entryOptionDescription(option)}
                      </p>
                    </div>
                    <span className="mt-3 inline-block text-[10px] font-semibold text-slate-300 bg-slate-800 px-2 py-1 rounded-md border border-slate-700">
                      Choose this option
                    </span>
                  </button>
                ))}
              </div>
              <p className="mt-3 text-[11px] text-slate-500">
                FormPilot will open only the path you choose. Dismissing this panel is not a
                choice, and no path is selected automatically.
              </p>
            </div>
          )}

          {/* Login method */}
          {activeGate.gate_type === 'LOGIN_METHOD' && (
            <div className="space-y-4">
              <p className="text-sm text-slate-300 leading-relaxed">{activeGate.description}</p>
              <div className="grid grid-cols-1 gap-2">
                {activeGate.options?.map((option, index) => (
                  <button
                    key={option.value || option.method || index}
                    type="button"
                    onClick={() => handleLoginMethodChoice(option)}
                    className="p-3.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/60 text-left transition-all flex items-center justify-between gap-3"
                  >
                    <div>
                      <div className="text-sm font-bold text-slate-100">
                        {option.label || option.text}
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {option.description || 'Use this method to sign in'}
                      </div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-amber-400 shrink-0" />
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-slate-500">
                The form supports more than one sign-in method. Choose the one that belongs to
                your account; FormPilot will not pick one for you.
              </p>
            </div>
          )}

          {/* Account identifier */}
          {activeGate.gate_type === 'ACCOUNT_IDENTIFIER' && (
            <div className="space-y-4">
              <p className="text-sm text-slate-300 leading-relaxed">{activeGate.description}</p>
              <div className="grid grid-cols-1 gap-2">
                {activeGate.options?.map((option, index) => (
                  <button
                    key={option.key || index}
                    type="button"
                    onClick={() => handleIdentifierChoice(option)}
                    className="p-3.5 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/60 text-left transition-all flex items-center justify-between gap-3"
                  >
                    <div>
                      <div className="text-sm font-bold text-slate-100">
                        {option.text || option.label || option.key}
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        Use this saved detail to identify the account
                      </div>
                    </div>
                    <ArrowRight className="w-4 h-4 text-amber-400 shrink-0" />
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-slate-500">
                FormPilot will not fill every identifier the form shows. Choose the one your
                account uses.
              </p>
            </div>
          )}

          {/* Verified fill check */}
          {activeGate.gate_type === 'FILL_INCOMPLETE' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/40 text-xs text-amber-100 leading-relaxed">
                <div className="flex items-center gap-2 font-bold text-amber-300 uppercase tracking-wider text-[10px] mb-1">
                  <AlertTriangle className="w-4 h-4" />
                  This form is not fully filled
                </div>
                {activeGate.description}
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-center">
                  <div className="text-lg font-bold text-emerald-300">
                    {activeGate.fill_summary?.verified || 0}
                  </div>
                  <div className="text-[9px] uppercase tracking-wider text-emerald-400/80">
                    Verified
                  </div>
                </div>
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-center">
                  <div className="text-lg font-bold text-red-300">
                    {activeGate.fill_summary?.failed || 0}
                  </div>
                  <div className="text-[9px] uppercase tracking-wider text-red-400/80">Failed</div>
                </div>
                <div className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-center">
                  <div className="text-lg font-bold text-slate-300">
                    {activeGate.fill_summary?.skipped || 0}
                  </div>
                  <div className="text-[9px] uppercase tracking-wider text-slate-500">Skipped</div>
                </div>
              </div>

              {activeGate.fill_failures?.length > 0 && (
                <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="pb-2">Field</th>
                        <th className="pb-2">Status</th>
                        <th className="pb-2 text-right">Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {activeGate.fill_failures.map((failure, index) => (
                        <tr key={index}>
                          <td className="py-1.5 text-slate-300">{failure.field_label}</td>
                          <td className={`py-1.5 font-bold ${failure.status === 'FAILED' ? 'text-red-400' : 'text-amber-400'}`}>
                            {failure.status}
                          </td>
                          <td className="py-1.5 text-right font-sans text-[10px] text-slate-500">
                            {failure.reason}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => onSubmitResponse({ action: 'CONTINUE' })}
                  className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  Continue after reviewing
                </button>
                <button
                  type="button"
                  onClick={() => onSubmitResponse({ action: 'FILL_RECHECK' })}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-extrabold text-sm flex items-center gap-2"
                >
                  <RefreshCw className="w-4 h-4" />
                  <span>Recheck and fill again</span>
                </button>
              </div>
            </div>
          )}

          {/* Missing field */}
          {activeGate.gate_type === 'MISSING_FIELD' && (
            <form onSubmit={handleMissingFieldSubmit} className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <p className="text-xs text-slate-400 leading-relaxed">
                  This form asks for a detail that is not saved yet. Enter it once and FormPilot
                  will remember it for future applications.
                </p>
                <div className="mt-3">
                  <label className="text-[10px] font-bold text-amber-300 block mb-1 uppercase tracking-wider">
                    {activeGate.field_label}
                  </label>
                  <input
                    type={activeGate.input_type === 'date' ? 'date' : activeGate.input_type || 'text'}
                    value={inputVal}
                    onChange={(event) => setInputVal(event.target.value)}
                    autoFocus
                    placeholder={`Enter ${activeGate.field_label}`}
                    className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:border-amber-500 focus:ring-1 focus:ring-amber-500 text-white font-medium text-sm outline-none"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-3 pt-1">
                <button
                  type="submit"
                  disabled={!inputVal.trim()}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg disabled:opacity-50"
                >
                  <Sparkles className="w-4 h-4" />
                  <span>Save and fill this field</span>
                </button>
              </div>
            </form>
          )}

          {/* Unknown field: never guess */}
          {activeGate.gate_type === 'UNKNOWN_FIELD' && (
            <form onSubmit={handleUnknownFieldSubmit} className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <p className="text-xs text-slate-300 leading-relaxed">
                  {activeGate.description}
                </p>
                <div className="text-[11px] font-mono text-slate-500">
                  {activeGate.why || 'No high-confidence match in the field registry.'}
                </div>
                <div>
                  <label className="text-[10px] font-bold text-amber-300 block mb-1 uppercase tracking-wider">
                    {activeGate.field_label}
                    {activeGate.required && <span className="text-red-400 ml-1">required</span>}
                  </label>
                  {activeGate.options?.length ? (
                    <select
                      value={inputVal}
                      onChange={(event) => setInputVal(event.target.value)}
                      className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:border-amber-500 text-white font-medium text-sm outline-none"
                    >
                      <option value="">Choose an option</option>
                      {activeGate.options.map((option, index) => (
                        <option key={index} value={option.value || option.text}>
                          {option.text || option.value}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={activeGate.input_type === 'date' ? 'date' : activeGate.input_type || 'text'}
                      value={inputVal}
                      onChange={(event) => setInputVal(event.target.value)}
                      autoFocus
                      placeholder={`Enter ${activeGate.field_label}`}
                      className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:border-amber-500 focus:ring-1 focus:ring-amber-500 text-white font-medium text-sm outline-none"
                    />
                  )}
                </div>
                <p className="text-[11px] text-slate-500">
                  The value is stored as a custom profile field for this account. It is not added
                  to shared recipes.
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  {activeGate.can_skip && (
                    <button
                      type="button"
                      onClick={() => onSubmitResponse({ action: 'SKIP' })}
                      className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                    >
                      Skip this field
                    </button>
                  )}
                  {hasLive && (
                    <button
                      type="button"
                      onClick={() => onSubmitResponse({ action: 'CONTINUE' })}
                      className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                    >
                      I filled it in the browser
                    </button>
                  )}
                </div>
                <button
                  type="submit"
                  disabled={!inputVal.trim()}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 disabled:opacity-50"
                >
                  <Sparkles className="w-4 h-4" />
                  <span>Use this value</span>
                </button>
              </div>
            </form>
          )}

          {/* Text CAPTCHA */}
          {activeGate.gate_type === 'CAPTCHA_SOLVE' && (
            <form onSubmit={handleCaptchaSubmit} className="space-y-4">
              <p className="text-xs text-slate-300">{activeGate.description}</p>
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col md:flex-row items-center gap-4 justify-center">
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
                    onChange={(event) => setCaptchaVal(event.target.value)}
                    autoFocus
                    placeholder="Enter the characters"
                    className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 focus:border-amber-500 text-center text-lg font-mono font-bold tracking-widest text-amber-300 outline-none"
                  />
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                {hasLive && (
                  <button
                    type="button"
                    onClick={() => onSubmitResponse({ action: 'HANDOFF_COMPLETE' })}
                    className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold border border-slate-700"
                  >
                    I solved it in the live browser
                  </button>
                )}
                <button
                  type="submit"
                  disabled={!captchaVal.trim()}
                  className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 disabled:opacity-50"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Submit and continue</span>
                </button>
              </div>
            </form>
          )}

          {/* Interactive human handoff: CAPTCHA / slider / grid / puzzle */}
          {activeGate.gate_type === 'LIVE_HANDOFF' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-amber-500/30">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300 shrink-0">
                    <Lock className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-200 font-semibold">
                      A human must complete this security check.
                    </p>
                    <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                      {activeGate.description}
                    </p>
                  </div>
                </div>
                {activeGate.detected_types?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {activeGate.detected_types.map((type) => (
                      <span
                        key={type}
                        className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-amber-300 border border-slate-700 uppercase"
                      >
                        {type}
                      </span>
                    ))}
                  </div>
                )}
                {activeGate.captcha_prompt && (
                  <p className="mt-3 text-[11px] text-slate-500 font-mono line-clamp-2">
                    {activeGate.captcha_prompt}
                  </p>
                )}
              </div>

              {instructions.length > 0 && (
                <ol className="space-y-2">
                  {instructions.map((instruction, index) => (
                    <li key={index} className="flex items-start gap-2 text-xs text-slate-300">
                      <span className="w-5 h-5 rounded-full bg-slate-800 border border-slate-700 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                        {index + 1}
                      </span>
                      <span className="leading-relaxed">{instruction}</span>
                    </li>
                  ))}
                </ol>
              )}

              <div className="rounded-xl bg-slate-950 border border-slate-800 px-3 py-2 text-[11px] text-slate-500">
                Policy: {activeGate.solver_policy === 'human_handoff_only'
                  ? 'human handoff only — no automatic solving, token injection or evasion.'
                  : 'human decision required.'}
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                <button
                  type="button"
                  onClick={hidePanel}
                  className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  Back to the live page
                </button>
                <button
                  type="button"
                  onClick={() => onSubmitResponse({ action: 'HANDOFF_COMPLETE' })}
                  className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold text-sm flex items-center gap-2"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>I completed this step</span>
                </button>
              </div>
            </div>
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
                    <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
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
                  <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <BellRing className="w-4 h-4 text-emerald-400 shrink-0" />
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-slate-200">Phone alert channel</div>
                        <div className="text-[11px] font-mono text-emerald-400 truncate">
                          {activeGate.ntfy_url}
                        </div>
                      </div>
                    </div>
                    <a
                      href={activeGate.ntfy_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-[11px] font-bold flex items-center gap-1.5 shrink-0"
                    >
                      <span>Open</span>
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
                      className="text-amber-400 font-mono font-bold bg-amber-500/10 hover:bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/30 text-[11px]"
                    >
                      Use demo code: {demoOtp}
                    </button>
                  )}
                </div>
              </div>

              <div className="flex flex-col items-center gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={8}
                  value={otpVal}
                  onChange={(event) => setOtpVal(event.target.value)}
                  autoFocus
                  placeholder="Enter the code"
                  className="w-64 px-4 py-3 rounded-xl bg-slate-950 border-2 border-emerald-500/60 focus:border-emerald-400 text-center text-2xl font-mono font-extrabold tracking-widest text-emerald-300 outline-none shadow-lg shadow-emerald-500/10"
                />
                {hasLive && (
                  <button
                    type="button"
                    onClick={() => onSubmitResponse({ action: 'HANDOFF_COMPLETE' })}
                    className="text-[11px] font-semibold text-sky-300 hover:text-sky-200 underline decoration-dotted"
                  >
                    I entered the code directly in the live browser
                  </button>
                )}
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                <button
                  type="button"
                  onClick={dismissGate}
                  className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={!otpVal.trim()}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg shadow-emerald-500/20 disabled:opacity-50"
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
              {!editingSection ? (
                <>
                  <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 font-medium">
                    Section {activeGate.section_number} is ready. Check these details against the
                    live form before continuing. You can also edit any field directly in the
                    live browser.
                  </div>

                  {activeGate.fields_filled?.length > 0 ? (
                    <div className="max-h-52 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
                      <table className="w-full text-left text-xs font-mono">
                        <thead>
                          <tr className="border-b border-slate-800 text-slate-400">
                            <th className="pb-2">Field</th>
                            <th className="pb-2">Filled value</th>
                            <th className="pb-2 text-right">Source</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {activeGate.fields_filled.map((field, index) => (
                            <tr key={index} className="hover:bg-slate-900/50">
                              <td className="py-1.5 text-slate-300">{field.field_label}</td>
                              <td className="py-1.5 text-amber-300 font-semibold">{field.injected_value}</td>
                              <td className="py-1.5 text-right text-emerald-400 font-sans text-[10px]">
                                {field.provenance === 'user-entered-now' ? 'You' : 'Profile'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500">No fields were filled in this section.</p>
                  )}

                  <div className="flex items-center justify-between gap-3 pt-2 border-t border-slate-800">
                    {hasLive ? (
                      <button
                        type="button"
                        onClick={() => setEditingSection(true)}
                        className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                      >
                        I need to edit something
                      </button>
                    ) : (
                      <span />
                    )}
                    <button
                      type="button"
                      onClick={() => handleSectionApproval(true)}
                      className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 shadow-lg"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Confirm and continue</span>
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="p-4 rounded-xl bg-sky-500/10 border border-sky-500/40 text-xs text-sky-200 leading-relaxed">
                    <div className="flex items-center gap-2 font-bold text-sky-300 uppercase tracking-wider text-[10px] mb-1">
                      <MousePointer2 className="w-4 h-4" />
                      Agent paused for your edits
                    </div>
                    Edit fields directly in the live browser above. When the section looks right,
                    continue and FormPilot will move to the next step. Your edits are not
                    overwritten while this panel is open.
                  </div>
                  <div className="flex items-center justify-between gap-3 pt-1">
                    <button
                      type="button"
                      onClick={() => setEditingSection(false)}
                      className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                    >
                      Back to review
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSectionApproval(true)}
                      className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-extrabold text-sm flex items-center gap-2"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Done editing — continue</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Live photo / file upload */}
          {isUploadGate && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                  {activeGate.gate_type === 'LIVE_PHOTO' ? <Camera className="w-4 h-4 text-sky-300" /> : <Upload className="w-4 h-4 text-sky-300" />}
                  <span>{activeGate.field_label || 'Requested file'}</span>
                  {activeGate.live_photo_required && (
                    <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      live photo
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-2 leading-relaxed">{activeGate.description}</p>
                {instructions.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {instructions.map((instruction, index) => (
                      <li key={index} className="text-[11px] text-slate-500 flex items-start gap-1.5">
                        <span className="text-slate-600 mt-0.5">•</span>
                        <span>{instruction}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {cameraActive ? (
                <div className="rounded-2xl overflow-hidden bg-black border border-slate-700 relative">
                  <video ref={videoRef} playsInline muted className="w-full max-h-64 object-cover" />
                  <div className="absolute inset-x-0 bottom-0 p-2 flex items-center justify-center gap-2 bg-gradient-to-t from-black/80 to-transparent">
                    <button
                      type="button"
                      onClick={capturePhoto}
                      className="px-4 py-2 rounded-xl bg-white text-slate-950 text-xs font-extrabold flex items-center gap-1.5"
                    >
                      <Camera className="w-4 h-4" />
                      <span>Take photo</span>
                    </button>
                    <button
                      type="button"
                      onClick={stopCamera}
                      className="px-3 py-2 rounded-xl bg-slate-800/90 text-slate-200 text-xs font-semibold"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {photoPreview ? (
                    <div className="rounded-2xl overflow-hidden bg-slate-950 border border-slate-700 relative">
                      {photoFile?.type?.startsWith('image/') ? (
                        <img src={photoPreview} alt="Selected file preview" className="w-full max-h-64 object-contain" />
                      ) : (
                        <div className="flex items-center gap-3 px-4 py-6">
                          <FileUp className="w-7 h-7 text-sky-300 shrink-0" />
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-slate-200 truncate">
                              {photoFile?.name || 'Selected file'}
                            </div>
                            <div className="text-[10px] font-mono text-slate-500">
                              {photoFile ? `${Math.ceil(photoFile.size / 1024)} KB` : ''}
                            </div>
                          </div>
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="absolute top-2 right-2 p-1.5 rounded-lg bg-slate-950/80 hover:bg-slate-900 text-slate-200 border border-slate-700"
                        title="Choose a different file"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ) : (
                    <div className="rounded-2xl border-2 border-dashed border-slate-700 bg-slate-950/60 p-6 text-center">
                      <ImageIcon className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                      <p className="text-xs text-slate-400">
                        {activeGate.gate_type === 'LIVE_PHOTO'
                          ? 'Use your camera for a live photo, or choose a recent photo of yourself.'
                          : 'Choose the file the portal asks for.'}
                      </p>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-2">
                    {activeGate.gate_type === 'LIVE_PHOTO' && (
                      <button
                        type="button"
                        onClick={startCamera}
                        className="px-3 py-2 rounded-xl bg-sky-500/20 hover:bg-sky-500/30 text-sky-200 border border-sky-500/40 text-xs font-bold flex items-center gap-1.5"
                      >
                        <Camera className="w-3.5 h-3.5" />
                        <span>Use my camera</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-bold flex items-center gap-1.5"
                    >
                      <FileUp className="w-3.5 h-3.5" />
                      <span>{photoPreview ? 'Choose another file' : 'Choose a file'}</span>
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={activeGate.accept || 'image/*,application/pdf'}
                      capture={activeGate.gate_type === 'LIVE_PHOTO' ? 'user' : undefined}
                      onChange={chooseFile}
                      className="hidden"
                    />
                    <span className="text-[10px] text-slate-500 font-mono">
                      {activeGate.accept || 'JPG, PNG, WEBP or PDF'} · max {activeGate.max_size_mb || 5} MB
                    </span>
                  </div>
                </>
              )}

              {cameraError && (
                <div className="flex items-start gap-2 rounded-xl bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-[11px] text-amber-200">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{cameraError}</span>
                </div>
              )}
              {uploadError && (
                <div className="flex items-start gap-2 rounded-xl bg-red-500/10 border border-red-500/30 px-3 py-2 text-[11px] text-red-200">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{uploadError}</span>
                </div>
              )}

              {activeGate.privacy_note && (
                <p className="text-[10px] text-slate-500">{activeGate.privacy_note}</p>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                {hasLive && (
                  <button
                    type="button"
                    onClick={() => onSubmitResponse({ action: 'UPLOAD_COMPLETE', field_key: activeGate.field_key })}
                    className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                  >
                    I attached it in the live browser
                  </button>
                )}
                <button
                  type="button"
                  onClick={submitUpload}
                  disabled={!photoFile || uploading}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-sky-500 to-cyan-500 hover:from-sky-400 hover:to-cyan-400 text-slate-950 font-extrabold text-sm flex items-center gap-2 disabled:opacity-50"
                >
                  {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                  <span>{uploading ? 'Attaching…' : 'Attach to the live portal'}</span>
                </button>
              </div>
            </div>
          )}

          {/* Safety handover: payment or final submission */}
          {activeGate.gate_type === 'PRE_PAYMENT_SAFETY_LOCK' && (
            <div className="space-y-4">
              <div className="p-4 rounded-2xl bg-red-500/10 border-2 border-red-500/50 text-red-200">
                <div className="flex items-center gap-2 text-xs font-extrabold text-red-400 uppercase tracking-wide">
                  <ShieldAlert className="w-5 h-5" />
                  <span>{activeGate.final_action === 'submission' ? 'Nothing was submitted' : 'Payment was not started'}</span>
                </div>
                <p className="text-xs text-red-300/90 mt-2 leading-relaxed">{activeGate.description}</p>
              </div>

              {hasLive && (
                <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-[11px] text-sky-200 leading-relaxed">
                  The live browser is on the right. Complete the payment or final submission
                  yourself there. FormPilot will not click the payment or submit button, and it
                  will not fill card, UPI or OTP details.
                </div>
              )}

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
                <div className="flex items-center justify-between mb-2 gap-2">
                  <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">
                    Details check before you continue
                  </span>
                  <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-mono">
                    {activeGate.total_verified_fields} of {activeGate.total_checked_fields || activeGate.total_verified_fields} checked
                  </span>
                </div>
                <div className="max-h-48 overflow-y-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="pb-2">Field</th>
                        <th className="pb-2">Saved value</th>
                        <th className="pb-2 text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {activeGate.audit_diff?.map((record, index) => (
                        <tr key={index}>
                          <td className="py-1.5 text-slate-300">{record.field}</td>
                          <td className="py-1.5 text-amber-300 font-semibold">{record.vault_value}</td>
                          <td className={`py-1.5 text-right font-bold ${statusClass(record.status)}`}>
                            {statusLabel(record.status)}
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
                FormPilot never pays or submits.
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                {activeGate.run_id ? (
                  <a
                    href={`/api/runs/${activeGate.run_id}/audit`}
                    className="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-semibold border border-slate-700 flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download details</span>
                  </a>
                ) : (
                  <span />
                )}
                <button
                  type="button"
                  onClick={() => onSubmitResponse({ action: 'ACKNOWLEDGE_LOCK' })}
                  className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold border border-slate-700"
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
                <span className="text-[10px] font-bold text-slate-300 uppercase tracking-wider">
                  How would you like to continue?
                </span>
                <div className="grid grid-cols-1 gap-2">
                  {activeGate.suggested_actions?.map((action, index) => (
                    <button
                      key={index}
                      type="button"
                      onClick={() => onSubmitResponse({ action: 'ERROR_RECOVERY', choice: action })}
                      className="p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 text-left text-xs text-slate-200 font-medium transition-all flex items-center justify-between"
                    >
                      <span>{action}</span>
                      <ArrowRight className="w-3.5 h-3.5 text-amber-400" />
                    </button>
                  ))}
                </div>
              </div>
              {hasLive && (
                <p className="text-[11px] text-slate-500">
                  You can correct the highlighted field in the live browser before choosing
                  “Try again”.
                </p>
              )}
            </div>
          )}

          {/* Fallback */}
          {!LIVE_GATES.has(activeGate.gate_type)
            && !['GATEWAY_DECISION', 'LOGIN_METHOD', 'ACCOUNT_IDENTIFIER', 'FILL_INCOMPLETE', 'MISSING_FIELD', 'CAPTCHA_SOLVE', 'OTP_RELAY', 'SECTION_APPROVAL', 'PRE_PAYMENT_SAFETY_LOCK', 'ERROR_DIAGNOSIS'].includes(activeGate.gate_type) && (
              <div className="space-y-4 text-center py-2">
                <p className="text-sm text-slate-300">
                  {activeGate.description || 'FormPilot is waiting for your confirmation to continue.'}
                </p>
                <div className="flex justify-center gap-3">
                  <button
                    type="button"
                    onClick={() => onSubmitResponse({ action: 'CONTINUE' })}
                    className="px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-sm"
                  >
                    Continue
                  </button>
                  <button
                    type="button"
                    onClick={dismissGate}
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
