import React, { useState, useEffect } from 'react';
import {
  X,
  Image as ImageIcon,
  CheckCircle2,
  Upload,
  AlertCircle,
  Sparkles,
  Sliders,
  Maximize2,
  ShieldCheck,
  Check,
} from 'lucide-react';
import {
  BiometricFaceScanIcon,
  BiometricFingerprintIcon,
  SecurityShieldIcon,
  UPSCSealIcon,
  SSCSealIcon,
  RailwaySealIcon,
} from './CustomIcons';

const AGENCY_PRESETS = [
  {
    id: 'upsc',
    name: 'UPSC Civil Services',
    icon: UPSCSealIcon,
    photoDim: '350 x 350 px',
    photoRange: '20 KB – 50 KB',
    sigDim: '140 x 60 px',
    sigRange: '10 KB – 20 KB',
  },
  {
    id: 'ssc',
    name: 'SSC CGL / CHSL',
    icon: SSCSealIcon,
    photoDim: '350 x 350 px',
    photoRange: '20 KB – 50 KB',
    sigDim: '140 x 60 px',
    sigRange: '10 KB – 20 KB',
  },
  {
    id: 'rrb',
    name: 'Railway RRB NTPC',
    icon: RailwaySealIcon,
    photoDim: '200 x 200 px',
    photoRange: '20 KB – 50 KB',
    sigDim: '140 x 60 px',
    sigRange: '10 KB – 20 KB',
  },
];

export default function BiometricsStudio(props) {
  if (!props.isOpen) return null;
  return <BiometricsContent {...props} />;
}

function BiometricsContent({ onClose }) {
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
      }
    } catch (err) {
      console.error('Photo compression error:', err);
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
      }
    } catch (err) {
      console.error('Signature compression error:', err);
    } finally {
      setUploadingSig(false);
    }
  };

  const activePresetConfig = AGENCY_PRESETS.find((p) => p.id === selectedPreset) || AGENCY_PRESETS[0];

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#07090e]/80 backdrop-blur-xl animate-fadeIn">
      <div className="glass-panel-elevated specular-top border border-white/[0.12] rounded-3xl max-w-3xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        
        {/* Header */}
        <div className="px-6 py-4 bg-white/[0.02] border-b border-white/[0.08] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-300 shadow-inner">
              <BiometricFaceScanIcon className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-extrabold text-white">Biometrics Calibration Studio</h2>
                <span className="text-[10px] bg-indigo-500/15 text-indigo-300 px-2.5 py-0.5 rounded-full border border-indigo-500/30 uppercase tracking-wider font-mono font-bold">
                  Lossless DP Engine
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                EXIF stripper, aspect-ratio normalizer, and DPI optimizer tailored to Indian recruitment guidelines
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors"
            title="Close studio"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Agency Presets Selector Bar */}
        <div className="px-6 py-3 bg-white/[0.015] border-b border-white/[0.06] flex items-center justify-between gap-2 overflow-x-auto shrink-0">
          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-bold shrink-0">
            Active Agency Target:
          </span>
          <div className="flex items-center gap-2">
            {AGENCY_PRESETS.map((preset) => {
              const Icon = preset.icon;
              const isSelected = selectedPreset === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => setSelectedPreset(preset.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    isSelected
                      ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-200 shadow-sm shadow-indigo-500/20'
                      : 'bg-white/[0.03] border-white/[0.08] text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{preset.name}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          
          {/* Section 1: Photograph Studio */}
          <div className="p-5 rounded-2xl glass-panel border border-white/[0.08] space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <BiometricFaceScanIcon className="w-4 h-4 text-indigo-400" />
                  <span>Passport Photograph</span>
                  <span className="text-xs text-indigo-300 font-mono font-semibold">
                    ({activePresetConfig.photoRange} • {activePresetConfig.photoDim})
                  </span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Removes camera EXIF tags, centers facial landmarks, and fits target byte boundaries.
                </p>
              </div>
              <label className="cursor-pointer px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-400 hover:to-violet-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-500/20 transition-all">
                <Upload className="w-3.5 h-3.5" />
                <span>{uploadingPhoto ? 'Optimizing...' : 'Upload & Calibrate'}</span>
                <input type="file" accept="image/*" onChange={handlePhotoUpload} className="hidden" />
              </label>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-5 pt-1">
              <div className="relative group w-36 h-36 rounded-2xl bg-slate-950/90 border-2 border-dashed border-white/[0.14] flex items-center justify-center overflow-hidden shrink-0 shadow-inner">
                {photoCompressResult?.data_uri ? (
                  <img
                    src={photoCompressResult.data_uri}
                    alt="Optimized Candidate Photo"
                    className="w-full h-full object-cover"
                  />
                ) : previews?.photo?.path ? (
                  <img
                    src={`${previews.photo.path}?t=${Date.now()}`}
                    alt="Current Photo"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <span className="text-xs text-slate-500">No Photo</span>
                )}
                {(photoCompressResult?.data_uri || previews?.photo?.path) && (
                  <button
                    type="button"
                    onClick={() =>
                      setLightboxImage(
                        photoCompressResult?.data_uri || `${previews?.photo?.path}?t=${Date.now()}`
                      )
                    }
                    className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity"
                    title="Zoom preview"
                  >
                    <Maximize2 className="w-5 h-5" />
                  </button>
                )}
              </div>

              <div className="flex-1 w-full space-y-2 text-xs font-mono">
                <div className="flex justify-between py-1.5 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Current Byte Size:</span>
                  <span className={`font-bold ${isPhotoCompliant ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {photoSizeKb !== null ? `${photoSizeKb} KB` : '—'}
                  </span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Target Ceiling:</span>
                  <span className="text-slate-300 font-bold">{activePresetConfig.photoRange}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Dimensions:</span>
                  <span className="text-slate-300 font-bold">{activePresetConfig.photoDim}</span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-1.5 font-sans font-bold">
                    {isPhotoCompliant ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span className="text-emerald-400">Compliant with {activePresetConfig.name}</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="w-4 h-4 text-amber-400" />
                        <span className="text-amber-300">Upload photo to verify compliance</span>
                      </>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">EXIF Stripped ✓</span>
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Signature Studio */}
          <div className="p-5 rounded-2xl glass-panel border border-white/[0.08] space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <BiometricFingerprintIcon className="w-4 h-4 text-indigo-400" />
                  <span>Digital Signature</span>
                  <span className="text-xs text-indigo-300 font-mono font-semibold">
                    ({activePresetConfig.sigRange} • {activePresetConfig.sigDim})
                  </span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Isolates ink stroke from notebook texture and converts to pure high-contrast grayscale.
                </p>
              </div>
              <label className="cursor-pointer px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-400 hover:to-violet-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-500/20 transition-all">
                <Upload className="w-3.5 h-3.5" />
                <span>{uploadingSig ? 'Optimizing...' : 'Upload & Calibrate'}</span>
                <input type="file" accept="image/*" onChange={handleSigUpload} className="hidden" />
              </label>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-5 pt-1">
              <div className="relative group w-48 h-20 rounded-2xl bg-white border-2 border-white/[0.14] flex items-center justify-center overflow-hidden shrink-0 shadow-inner p-1">
                {sigCompressResult?.data_uri ? (
                  <img
                    src={sigCompressResult.data_uri}
                    alt="Optimized Signature"
                    className="max-h-full object-contain"
                  />
                ) : previews?.signature?.path ? (
                  <img
                    src={`${previews.signature.path}?t=${Date.now()}`}
                    alt="Current Signature"
                    className="max-h-full object-contain"
                  />
                ) : (
                  <span className="text-xs text-slate-500">No Signature</span>
                )}
                {(sigCompressResult?.data_uri || previews?.signature?.path) && (
                  <button
                    type="button"
                    onClick={() =>
                      setLightboxImage(
                        sigCompressResult?.data_uri || `${previews?.signature?.path}?t=${Date.now()}`
                      )
                    }
                    className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity"
                    title="Zoom preview"
                  >
                    <Maximize2 className="w-5 h-5" />
                  </button>
                )}
              </div>

              <div className="flex-1 w-full space-y-2 text-xs font-mono">
                <div className="flex justify-between py-1.5 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Current Byte Size:</span>
                  <span className={`font-bold ${isSigCompliant ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {sigSizeKb !== null ? `${sigSizeKb} KB` : '—'}
                  </span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Target Ceiling:</span>
                  <span className="text-slate-300 font-bold">{activePresetConfig.sigRange}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Dimensions:</span>
                  <span className="text-slate-300 font-bold">{activePresetConfig.sigDim}</span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-1.5 font-sans font-bold">
                    {isSigCompliant ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span className="text-emerald-400">Compliant with {activePresetConfig.name}</span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="w-4 h-4 text-amber-400" />
                        <span className="text-amber-300">Upload signature to verify compliance</span>
                      </>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">Background Cleared ✓</span>
                </div>
              </div>
            </div>
          </div>

        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-white/[0.02] border-t border-white/[0.08] flex items-center justify-between">
          <span className="text-xs text-slate-400 flex items-center gap-1.5">
            <SecurityShieldIcon className="w-3.5 h-3.5 text-emerald-400" />
            <span>Images saved locally in <code className="font-mono text-slate-300">/data/biometrics/</code></span>
          </span>
          <button
            onClick={onClose}
            className="px-6 py-2.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-slate-200 text-xs font-semibold border border-white/[0.1] transition-all"
          >
            Done
          </button>
        </div>

      </div>

      {/* Lightbox Modal */}
      {lightboxImage && (
        <div
          className="fixed inset-0 z-60 bg-black/80 backdrop-blur-md flex items-center justify-center p-6"
          onClick={() => setLightboxImage(null)}
        >
          <div className="relative max-w-xl max-h-[80vh] p-3 rounded-2xl bg-slate-900 border border-white/[0.2] shadow-2xl">
            <img src={lightboxImage} alt="Expanded Preview" className="max-h-[70vh] object-contain rounded-xl" />
            <button
              onClick={() => setLightboxImage(null)}
              className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white hover:bg-black/80"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
