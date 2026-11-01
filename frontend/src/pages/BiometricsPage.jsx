import React, { useState, useEffect } from 'react';
import {
  Upload,
  Sparkles,
  Sliders,
  Maximize2,
  ShieldCheck,
  Check,
  AlertCircle,
  FileCheck2,
  ChevronRight,
  ZoomIn,
  RefreshCw,
  Info,
} from 'lucide-react';
import {
  BiometricFaceScanIcon,
  BiometricFingerprintIcon,
  SecurityShieldIcon,
  UPSCSealIcon,
  SSCSealIcon,
  RailwaySealIcon,
} from '../components/CustomIcons';

const AGENCY_PRESETS = [
  {
    id: 'upsc',
    name: 'UPSC Civil Services / NDA / CDS',
    icon: UPSCSealIcon,
    photoDim: '350 x 350 px',
    photoRange: '20 KB – 50 KB',
    sigDim: '140 x 60 px',
    sigRange: '10 KB – 20 KB',
  },
  {
    id: 'ssc',
    name: 'SSC CGL / CHSL / MTS',
    icon: SSCSealIcon,
    photoDim: '350 x 350 px',
    photoRange: '20 KB – 50 KB',
    sigDim: '140 x 60 px',
    sigRange: '10 KB – 20 KB',
  },
  {
    id: 'rrb',
    name: 'Railway RRB NTPC / Group D',
    icon: RailwaySealIcon,
    photoDim: '200 x 200 px',
    photoRange: '20 KB – 50 KB',
    sigDim: '140 x 60 px',
    sigRange: '10 KB – 20 KB',
  },
];

export default function BiometricsPage({ notify }) {
  const [previews, setPreviews] = useState(null);
  const [photoCompressResult, setPhotoCompressResult] = useState(null);
  const [sigCompressResult, setSigCompressResult] = useState(null);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [uploadingSig, setUploadingSig] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('upsc');
  const [lightboxImage, setLightboxImage] = useState(null);

  useEffect(() => {
    fetchPreviews();
  }, []);

  const fetchPreviews = async () => {
    try {
      const res = await fetch('/api/biometrics/preview');
      if (res.ok) {
        const data = await res.json();
        setPreviews(data);
      }
    } catch (err) {
      console.error('Error fetching biometrics preview:', err);
    }
  };

  const handlePhotoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingPhoto(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/biometrics/compress-photo', {
        method: 'POST',
        body: fd,
      });
      if (res.ok) {
        const data = await res.json();
        setPhotoCompressResult(data);
        fetchPreviews();
        if (notify) notify('Photograph losslessly calibrated to official recruitment standards.', 'success');
      } else {
        if (notify) notify('Photo compression failed. Check file format.', 'error');
      }
    } catch (err) {
      console.error('Photo compression error:', err);
      if (notify) notify('Network error while processing photo.', 'error');
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleSigUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingSig(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/biometrics/compress-signature', {
        method: 'POST',
        body: fd,
      });
      if (res.ok) {
        const data = await res.json();
        setSigCompressResult(data);
        fetchPreviews();
        if (notify) notify('Signature calibrated and contrast-enhanced.', 'success');
      } else {
        if (notify) notify('Signature compression failed. Check file format.', 'error');
      }
    } catch (err) {
      console.error('Signature compression error:', err);
      if (notify) notify('Network error while processing signature.', 'error');
    } finally {
      setUploadingSig(false);
    }
  };

  const photoSizeKb = photoCompressResult
    ? Number(photoCompressResult.compressed_size_kb)
    : previews?.photo?.size_kb
      ? Number(previews.photo.size_kb)
      : null;

  const sigSizeKb = sigCompressResult
    ? Number(sigCompressResult.compressed_size_kb)
    : previews?.signature?.size_kb
      ? Number(previews.signature.size_kb)
      : null;

  const isPhotoCompliant = photoSizeKb !== null && photoSizeKb >= 18 && photoSizeKb <= 52;
  const isSigCompliant = sigSizeKb !== null && sigSizeKb >= 8 && sigSizeKb <= 22;

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      {/* Top Breadcrumb & Header Bar */}
      <div className="px-6 py-5 border-b border-white/[0.08] bg-slate-950/40 backdrop-blur-md shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1">
              <span>Workstation</span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-violet-400 font-semibold">Biometrics Studio</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-white tracking-tight">Biometrics Calibration Studio</h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-violet-500/10 text-violet-300 border border-violet-500/30">
                <Sliders className="w-3 h-3" />
                Lossless DP Compression Engine
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={fetchPreviews}
              className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
              <span>Refresh Previews</span>
            </button>
          </div>
        </div>
      </div>

      <div className="p-6 max-w-6xl w-full mx-auto space-y-6">
        {/* Preset Selector Banner */}
        <div className="glass-panel p-5 rounded-3xl border border-white/[0.08] space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider font-mono">
              Target Agency Specification Presets
            </span>
            <span className="text-[10px] text-slate-400 font-mono">Auto-configures pixel bounds & file budgets</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {AGENCY_PRESETS.map((preset) => {
              const IconComp = preset.icon;
              const isSelected = selectedPreset === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => setSelectedPreset(preset.id)}
                  className={`p-4 rounded-2xl border text-left transition-all ${
                    isSelected
                      ? 'bg-indigo-500/15 border-indigo-400/50 shadow-sm shadow-indigo-500/20'
                      : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.05] hover:border-white/[0.12]'
                  }`}
                >
                  <div className="flex items-center gap-2.5 mb-2">
                    <IconComp className="w-5 h-5 text-indigo-300" />
                    <span className="text-xs font-bold text-white truncate">{preset.name}</span>
                  </div>
                  <div className="space-y-1 text-[11px] font-mono text-slate-400">
                    <div className="flex justify-between">
                      <span>Photo:</span>
                      <span className="text-slate-200">{preset.photoDim} ({preset.photoRange})</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Signature:</span>
                      <span className="text-slate-200">{preset.sigDim} ({preset.sigRange})</span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Dual Calibration Bays */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Photograph Calibration Bay */}
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] flex flex-col space-y-4">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-300">
                  <BiometricFaceScanIcon className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Passport Photograph Bay</h3>
                  <p className="text-[11px] text-slate-400">White background, front-facing biometric framing</p>
                </div>
              </div>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold border ${
                  isPhotoCompliant
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                }`}
              >
                {isPhotoCompliant ? 'UPSC/SSC Compliant' : 'Calibration Required'}
              </span>
            </div>

            {/* Photo Canvas Area */}
            <div className="relative aspect-square max-w-[280px] mx-auto w-full rounded-2xl bg-slate-950/90 border border-white/[0.1] overflow-hidden flex items-center justify-center shadow-inner group">
              {previews?.photo?.url ? (
                <>
                  <img
                    src={previews.photo.url}
                    alt="Candidate Photograph"
                    className="w-full h-full object-cover"
                  />
                  <button
                    type="button"
                    onClick={() => setLightboxImage(previews.photo.url)}
                    className="absolute bottom-2 right-2 p-2 rounded-xl bg-slate-900/80 backdrop-blur-md text-white border border-white/10 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Inspect Full Resolution"
                  >
                    <ZoomIn className="w-4 h-4" />
                  </button>
                </>
              ) : (
                <div className="text-center p-6 text-slate-500">
                  <BiometricFaceScanIcon className="w-12 h-12 mx-auto mb-2 opacity-30 text-slate-400" />
                  <span className="text-xs font-mono">No photo loaded</span>
                </div>
              )}
            </div>

            {/* Photo Telemetry Stats */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <span className="text-[10px] font-mono text-slate-400 block mb-0.5">Current File Size</span>
                <span className="font-mono font-bold text-white">
                  {photoSizeKb ? `${photoSizeKb} KB` : 'N/A'}
                </span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <span className="text-[10px] font-mono text-slate-400 block mb-0.5">Target Budget</span>
                <span className="font-mono font-bold text-indigo-300">20 KB – 50 KB</span>
              </div>
            </div>

            {/* Upload & Re-compress Action */}
            <div className="mt-auto pt-2">
              <label className="w-full py-3 px-4 rounded-xl border border-dashed border-white/20 hover:border-indigo-400 bg-white/[0.02] hover:bg-white/[0.04] text-xs font-semibold text-slate-300 hover:text-white flex items-center justify-center gap-2 cursor-pointer transition-colors">
                <Upload className="w-4 h-4 text-indigo-400" />
                <span>{uploadingPhoto ? 'Compressing to standard...' : 'Upload & Lossless Calibrate Photo'}</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/jpg"
                  onChange={handlePhotoUpload}
                  disabled={uploadingPhoto}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          {/* Signature Calibration Bay */}
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] flex flex-col space-y-4">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-violet-500/15 border border-violet-500/30 flex items-center justify-center text-violet-300">
                  <BiometricFingerprintIcon className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Signature Calibration Bay</h3>
                  <p className="text-[11px] text-slate-400">Black/blue ink on white paper, contrast-enhanced</p>
                </div>
              </div>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold border ${
                  isSigCompliant
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                    : 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                }`}
              >
                {isSigCompliant ? 'UPSC/SSC Compliant' : 'Calibration Required'}
              </span>
            </div>

            {/* Signature Canvas Area */}
            <div className="relative aspect-[3/1] max-w-[360px] mx-auto w-full rounded-2xl bg-slate-950/90 border border-white/[0.1] overflow-hidden flex items-center justify-center shadow-inner group">
              {previews?.signature?.url ? (
                <>
                  <img
                    src={previews.signature.url}
                    alt="Candidate Signature"
                    className="max-h-full max-w-full object-contain p-2"
                  />
                  <button
                    type="button"
                    onClick={() => setLightboxImage(previews.signature.url)}
                    className="absolute bottom-2 right-2 p-2 rounded-xl bg-slate-900/80 backdrop-blur-md text-white border border-white/10 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Inspect Signature Details"
                  >
                    <ZoomIn className="w-4 h-4" />
                  </button>
                </>
              ) : (
                <div className="text-center p-6 text-slate-500">
                  <BiometricFingerprintIcon className="w-10 h-10 mx-auto mb-1 opacity-30 text-slate-400" />
                  <span className="text-xs font-mono">No signature loaded</span>
                </div>
              )}
            </div>

            {/* Signature Telemetry Stats */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <span className="text-[10px] font-mono text-slate-400 block mb-0.5">Current File Size</span>
                <span className="font-mono font-bold text-white">
                  {sigSizeKb ? `${sigSizeKb} KB` : 'N/A'}
                </span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                <span className="text-[10px] font-mono text-slate-400 block mb-0.5">Target Budget</span>
                <span className="font-mono font-bold text-violet-300">10 KB – 20 KB</span>
              </div>
            </div>

            {/* Upload & Re-compress Action */}
            <div className="mt-auto pt-2">
              <label className="w-full py-3 px-4 rounded-xl border border-dashed border-white/20 hover:border-violet-400 bg-white/[0.02] hover:bg-white/[0.04] text-xs font-semibold text-slate-300 hover:text-white flex items-center justify-center gap-2 cursor-pointer transition-colors">
                <Upload className="w-4 h-4 text-violet-400" />
                <span>{uploadingSig ? 'Calibrating signature...' : 'Upload & Auto-Crop Signature'}</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/jpg"
                  onChange={handleSigUpload}
                  disabled={uploadingSig}
                  className="hidden"
                />
              </label>
            </div>
          </div>
        </div>

        {/* Technical Notice Ribbon */}
        <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.06] flex items-start gap-3 text-xs text-slate-400">
          <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
          <span>
            FormPilot's biometric processor uses DP-based dynamic quality scaling (PIL/LANCZOS) to ensure photos and signatures fit exact recruitment bounds without perceptible compression artifacts. Files are cached locally and injected automatically when file upload fields are matched.
          </span>
        </div>
      </div>

      {/* Lightbox inspection */}
      {lightboxImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md"
          onClick={() => setLightboxImage(null)}
        >
          <div className="relative max-w-2xl max-h-[85vh] p-4 bg-slate-950 border border-white/20 rounded-3xl overflow-hidden shadow-2xl">
            <img src={lightboxImage} alt="Biometric Inspection" className="max-w-full max-h-[75vh] object-contain rounded-xl" />
            <div className="mt-3 text-center text-xs text-slate-400 font-mono">
              Click anywhere to close full-resolution view
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
