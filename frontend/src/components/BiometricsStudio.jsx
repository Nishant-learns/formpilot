import React, { useState, useEffect } from 'react';
import { X, Image as ImageIcon, CheckCircle2, Upload, AlertCircle, Sparkles, Sliders } from 'lucide-react';

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
        body: fd
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
        body: fd
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#07090e]/80 backdrop-blur-xl animate-fadeIn">
      <div className="glass-panel-elevated specular-top border border-white/[0.12] rounded-3xl max-w-3xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="px-6 py-4 bg-white/[0.02] border-b border-white/[0.08] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-500/15 border border-violet-500/30 flex items-center justify-center text-violet-300">
              <ImageIcon className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-white flex items-center gap-2">
                <span>Biometric Studio</span>
                <span className="text-[10px] bg-violet-500/15 text-violet-300 px-2 py-0.5 rounded-full border border-violet-500/30 uppercase tracking-wider">
                  Automated Engine
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Precision image compression compliant with UPSC, SSC, and state recruitment specifications
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-slate-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          
          {/* Section 1: Photograph Studio */}
          <div className="p-4 rounded-2xl glass-panel space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                  <span>Passport photograph</span>
                  <span className="text-xs text-indigo-400 font-mono font-semibold">(20KB - 50KB JPEG • 350x350 px)</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Removes camera metadata, keeps the photo centered, and reduces the file size.
                </p>
              </div>
              <label className="cursor-pointer px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-400 hover:to-violet-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-500/20 transition-all">
                <Upload className="w-3.5 h-3.5" />
                <span>{uploadingPhoto ? 'Compressing...' : 'Upload photo'}</span>
                <input type="file" accept="image/*" onChange={handlePhotoUpload} className="hidden" />
              </label>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-5 pt-2">
              <div className="w-36 h-36 rounded-xl bg-slate-950/80 border-2 border-dashed border-white/[0.12] flex items-center justify-center overflow-hidden shrink-0 shadow-inner">
                {photoCompressResult?.data_uri ? (
                  <img src={photoCompressResult.data_uri} alt="Compressed Candidate Photo" className="w-full h-full object-cover" />
                ) : previews?.photo?.path ? (
                  <img src={`${previews.photo.path}?t=${Date.now()}`} alt="Current Photo" className="w-full h-full object-cover" />
                ) : (
                  <span className="text-xs text-slate-500">No Photo</span>
                )}
              </div>

              <div className="flex-1 w-full space-y-2 text-xs font-mono">
                <div className="flex justify-between py-1 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Current File Size:</span>
                  <span className="font-bold text-emerald-400">
                    {photoCompressResult ? `${photoCompressResult.compressed_size_kb} KB` : `${previews?.photo?.size_kb} KB`}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Target Constraint:</span>
                  <span className="text-slate-300">20.0 KB – 50.0 KB JPEG</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Dimensions:</span>
                  <span className="text-slate-300">350 x 350 px</span>
                </div>
                <div className="flex items-center gap-1.5 text-emerald-400 font-sans font-bold pt-1">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Ready to download and upload</span>
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Signature Studio */}
          <div className="p-4 rounded-2xl glass-panel space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                  <span>Digital signature</span>
                  <span className="text-xs text-indigo-400 font-mono font-semibold">(10KB - 20KB JPEG • 140x60 px)</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Flattens the background and improves contrast so the signature is easy to read.
                </p>
              </div>
              <label className="cursor-pointer px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-400 hover:to-violet-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-500/20 transition-all">
                <Upload className="w-3.5 h-3.5" />
                <span>{uploadingSig ? 'Compressing...' : 'Upload signature'}</span>
                <input type="file" accept="image/*" onChange={handleSigUpload} className="hidden" />
              </label>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-5 pt-2">
              <div className="w-48 h-20 rounded-xl bg-white border-2 border-white/[0.12] flex items-center justify-center overflow-hidden shrink-0 shadow-inner p-1">
                {sigCompressResult?.data_uri ? (
                  <img src={sigCompressResult.data_uri} alt="Compressed Signature" className="max-h-full object-contain" />
                ) : previews?.signature?.path ? (
                  <img src={`${previews.signature.path}?t=${Date.now()}`} alt="Current Signature" className="max-h-full object-contain" />
                ) : (
                  <span className="text-xs text-slate-500">No Signature</span>
                )}
              </div>

              <div className="flex-1 w-full space-y-2 text-xs font-mono">
                <div className="flex justify-between py-1 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Current File Size:</span>
                  <span className="font-bold text-emerald-400">
                    {sigCompressResult ? `${sigCompressResult.compressed_size_kb} KB` : `${previews?.signature?.size_kb} KB`}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Target Constraint:</span>
                  <span className="text-slate-300">10.0 KB – 20.0 KB JPEG</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/[0.08]">
                  <span className="text-slate-400 font-sans">Dimensions:</span>
                  <span className="text-slate-300">140 x 60 px</span>
                </div>
                <div className="flex items-center gap-1.5 text-emerald-400 font-sans font-bold pt-1">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Ready to download and upload</span>
                </div>
              </div>
            </div>
          </div>

        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-white/[0.02] border-t border-white/[0.08] flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-slate-200 text-xs font-semibold border border-white/[0.1] transition-all"
          >
            Done
          </button>
        </div>

      </div>
    </div>
  );
}
