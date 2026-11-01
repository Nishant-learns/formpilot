import React, { useState, useEffect, useRef } from 'react';
import {
  Save,
  RotateCcw,
  User,
  Phone,
  GraduationCap,
  Sparkles,
  Check,
  Download,
  Upload,
  Copy,
  CheckCheck,
  Shield,
  FileCheck2,
  Lock,
  ArrowRight,
  ChevronRight,
  AlertCircle,
  Plus,
  Trash2,
} from 'lucide-react';
import { SecurityShieldIcon, BiometricFingerprintIcon } from '../components/CustomIcons';

export default function VaultPage({ vault: initialVault, onVaultUpdate, notify }) {
  const [vault, setVault] = useState(initialVault || null);
  const [activeTab, setActiveTab] = useState('personal');
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);
  const [newCustomKey, setNewCustomKey] = useState('');
  const [newCustomVal, setNewCustomVal] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchVault();
  }, []);

  const fetchVault = async () => {
    try {
      const res = await fetch('/api/vault');
      if (res.ok) {
        const data = await res.json();
        setVault(data);
        if (onVaultUpdate) onVaultUpdate(data);
      }
    } catch (err) {
      console.error('Error fetching vault:', err);
    }
  };

  const handleSave = async () => {
    if (!vault) return;
    setSaving(true);
    try {
      const res = await fetch('/api/vault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vault),
      });
      if (res.ok) {
        setSaveSuccess(true);
        if (notify) notify('Identity profile saved to encrypted vault at rest.', 'success');
        if (onVaultUpdate) onVaultUpdate(vault);
        setTimeout(() => setSaveSuccess(false), 2400);
      } else {
        if (notify) notify('Failed to save identity profile.', 'error');
      }
    } catch (err) {
      console.error('Error saving vault:', err);
      if (notify) notify('Network error while saving vault.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Replace your saved details with the official demo profile? This cannot be undone.')) return;
    try {
      const res = await fetch('/api/vault/reset', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setVault(data.vault);
        if (onVaultUpdate) onVaultUpdate(data.vault);
        if (notify) notify('Vault reset to official demo profile.', 'info');
      }
    } catch (err) {
      console.error('Error resetting vault:', err);
    }
  };

  const copyToClipboard = (key, text) => {
    if (!text) return;
    navigator.clipboard?.writeText(String(text));
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1800);
  };

  const handleExportJson = () => {
    if (!vault) return;
    const blob = new Blob([JSON.stringify(vault, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `formpilot-vault-backup-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    if (notify) notify('Vault JSON exported to local downloads.', 'info');
  };

  const handleImportJson = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target.result);
        if (typeof data === 'object' && data !== null) {
          setVault(data);
          if (notify) notify('Profile imported into memory. Click "Save Changes" to commit.', 'info');
        }
      } catch (err) {
        if (notify) notify('Could not parse JSON file. Invalid format.', 'error');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleAddCustomField = () => {
    if (!newCustomKey.trim() || !newCustomVal.trim()) return;
    const sanitizedKey = newCustomKey.trim().toLowerCase().replace(/\s+/g, '_');
    setVault({
      ...vault,
      custom_fields: {
        ...(vault.custom_fields || {}),
        [sanitizedKey]: newCustomVal.trim(),
      },
    });
    setNewCustomKey('');
    setNewCustomVal('');
  };

  const handleDeleteCustomField = (keyToDelete) => {
    const updated = { ...(vault.custom_fields || {}) };
    delete updated[keyToDelete];
    setVault({ ...vault, custom_fields: updated });
  };

  // Validation checks
  const isAadhaarValid = vault?.aadhaar_number && /^\d{12}$/.test(vault.aadhaar_number.replace(/\s+/g, ''));
  const isPanValid = vault?.pan_card && /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(vault.pan_card.trim());
  const isMobileValid = vault?.mobile && /^\d{10}$/.test(vault.mobile.replace(/\D/g, ''));
  const isEmailValid = vault?.email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(vault.email);

  if (!vault) {
    return (
      <div className="flex-1 flex items-center justify-center p-12">
        <div className="flex items-center gap-3 text-slate-400 font-mono text-sm">
          <div className="w-5 h-5 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
          <span>Decrypting OneVault identity profile...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
      {/* Top Breadcrumb & Title Bar */}
      <div className="px-6 py-5 border-b border-white/[0.08] bg-slate-950/40 backdrop-blur-md shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1">
              <span>Workstation</span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-indigo-400 font-semibold">OneVault Identity</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-white tracking-tight">OneVault Identity Profile</h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                <Lock className="w-3 h-3" />
                AES-256 Encrypted At Rest
              </span>
            </div>
          </div>

          {/* Action Toolbar */}
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleImportJson}
              accept=".json"
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors"
            >
              <Upload className="w-3.5 h-3.5 text-slate-400" />
              <span>Import JSON</span>
            </button>
            <button
              type="button"
              onClick={handleExportJson}
              className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors"
            >
              <Download className="w-3.5 h-3.5 text-slate-400" />
              <span>Export JSON</span>
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.08] text-xs font-semibold text-slate-400 hover:text-amber-300 flex items-center gap-1.5 transition-colors"
              title="Reset to official demo profile"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset Profile</span>
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all shadow-sm ${
                saveSuccess
                  ? 'bg-emerald-600 text-white border border-emerald-500'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-400/40 shadow-indigo-500/20'
              }`}
            >
              {saveSuccess ? (
                <>
                  <Check className="w-4 h-4" />
                  <span>Saved to Vault!</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>{saving ? 'Saving...' : 'Save Profile Changes'}</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Readiness Metric Ribbon */}
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Profile Candidate</span>
            <span className="text-white font-bold truncate block">{vault.full_name || 'Not specified'}</span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Aadhaar Status</span>
            <span className={`font-mono font-bold flex items-center gap-1.5 ${isAadhaarValid ? 'text-emerald-400' : 'text-amber-400'}`}>
              {isAadhaarValid ? <Check className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
              {isAadhaarValid ? 'Valid 12-Digit' : 'Missing / Incomplete'}
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Contact Verification</span>
            <span className={`font-mono font-bold flex items-center gap-1.5 ${isMobileValid && isEmailValid ? 'text-emerald-400' : 'text-amber-400'}`}>
              {isMobileValid && isEmailValid ? <Check className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
              {isMobileValid && isEmailValid ? 'Verified Format' : 'Check Mobile/Email'}
            </span>
          </div>
          <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block mb-0.5">Academic Records</span>
            <span className="font-mono font-bold text-indigo-300">
              {vault.matric?.board ? `${vault.matric.board} (${vault.matric.percentage}%)` : 'Not configured'}
            </span>
          </div>
        </div>
      </div>

      {/* Main Form Tabs & Content Area */}
      <div className="p-6 max-w-6xl w-full mx-auto space-y-6">
        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-white/[0.08] pb-1 overflow-x-auto">
          {[
            { id: 'personal', label: '1. Identity & Demographics', icon: <User className="w-4 h-4" /> },
            { id: 'contact', label: '2. Contact & Domicile', icon: <Phone className="w-4 h-4" /> },
            { id: 'academic', label: '3. Educational Qualifications', icon: <GraduationCap className="w-4 h-4" /> },
            { id: 'custom', label: '4. Extended Portal Facts', icon: <Sparkles className="w-4 h-4" /> },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 rounded-xl text-xs font-semibold flex items-center gap-2 transition-all whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-indigo-500/20 text-indigo-200 border border-indigo-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04] border border-transparent'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab 1: Personal & Identity */}
        {activeTab === 'personal' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
              <div>
                <h3 className="text-sm font-bold text-white">Legal Identity & Personal Details</h3>
                <p className="text-xs text-slate-400">Values stored here are automatically injected into UPSC OTR, SSC OTR, RRB, and state recruitment portals.</p>
              </div>
              <span className="text-[10px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                Verified Clean
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 text-xs">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-slate-300 font-semibold">Full Candidate Name</label>
                  {vault.full_name && (
                    <button
                      type="button"
                      onClick={() => copyToClipboard('full_name', vault.full_name)}
                      className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1 font-mono"
                    >
                      {copiedKey === 'full_name' ? <CheckCheck className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedKey === 'full_name' ? 'Copied' : 'Copy'}</span>
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  value={vault.full_name || ''}
                  onChange={(e) => setVault({ ...vault, full_name: e.target.value, verify_full_name: e.target.value })}
                  placeholder="e.g. Aman Kumar Sharma"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Father's Name</label>
                <input
                  type="text"
                  value={vault.father_name || ''}
                  onChange={(e) => setVault({ ...vault, father_name: e.target.value, verify_father_name: e.target.value })}
                  placeholder="Father's full name"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Mother's Name</label>
                <input
                  type="text"
                  value={vault.mother_name || ''}
                  onChange={(e) => setVault({ ...vault, mother_name: e.target.value, verify_mother_name: e.target.value })}
                  placeholder="Mother's full name"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Date of Birth (YYYY-MM-DD)</label>
                <input
                  type="date"
                  value={vault.dob || ''}
                  onChange={(e) => setVault({ ...vault, dob: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Gender</label>
                <select
                  value={vault.gender || 'Male'}
                  onChange={(e) => setVault({ ...vault, gender: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                >
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Transgender">Transgender</option>
                </select>
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Social Category</label>
                <select
                  value={vault.category || 'UR'}
                  onChange={(e) => setVault({ ...vault, category: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                >
                  <option value="UR">UR (General / Unreserved)</option>
                  <option value="EWS">EWS (Economically Weaker Section)</option>
                  <option value="OBC-NCL">OBC-NCL (Other Backward Class)</option>
                  <option value="SC">SC (Scheduled Caste)</option>
                  <option value="ST">ST (Scheduled Tribe)</option>
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                    <span>Aadhaar Number</span>
                    {isAadhaarValid ? (
                      <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                        <Check className="w-3 h-3" /> 12-digit valid
                      </span>
                    ) : (
                      <span className="text-[10px] text-slate-500 font-mono">(12 digits)</span>
                    )}
                  </label>
                  {vault.aadhaar_number && (
                    <button
                      type="button"
                      onClick={() => copyToClipboard('aadhaar', vault.aadhaar_number)}
                      className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1 font-mono"
                    >
                      {copiedKey === 'aadhaar' ? <CheckCheck className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedKey === 'aadhaar' ? 'Copied' : 'Copy'}</span>
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  maxLength={14}
                  value={vault.aadhaar_number || ''}
                  onChange={(e) => setVault({ ...vault, aadhaar_number: e.target.value })}
                  placeholder="XXXX XXXX XXXX"
                  className={`w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border font-mono font-medium text-white focus:ring-1 outline-none transition-all ${
                    isAadhaarValid
                      ? 'border-emerald-500/40 focus:border-emerald-400 focus:ring-emerald-400/30'
                      : 'border-white/[0.1] focus:border-indigo-400 focus:ring-indigo-400/30'
                  }`}
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                    <span>PAN Card Number</span>
                    {isPanValid && (
                      <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                        <Check className="w-3 h-3" /> Valid PAN
                      </span>
                    )}
                  </label>
                </div>
                <input
                  type="text"
                  maxLength={10}
                  value={vault.pan_card || ''}
                  onChange={(e) => setVault({ ...vault, pan_card: e.target.value.toUpperCase() })}
                  placeholder="ABCDE1234F"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] font-mono font-medium text-white uppercase focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Domicile State</label>
                <input
                  type="text"
                  value={vault.domicile_state || ''}
                  onChange={(e) => setVault({ ...vault, domicile_state: e.target.value })}
                  placeholder="e.g. Haryana / Uttar Pradesh"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div className="md:col-span-2 lg:col-span-3">
                <label className="text-slate-300 font-semibold block mb-1.5">Visible Body Identification Mark</label>
                <input
                  type="text"
                  value={vault.identification_mark_1 || ''}
                  onChange={(e) => setVault({ ...vault, identification_mark_1: e.target.value })}
                  placeholder="e.g. A mole on the right cheek / A small scar on left forehead"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Contact & Address */}
        {activeTab === 'contact' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="border-b border-white/[0.06] pb-3">
              <h3 className="text-sm font-bold text-white">Contact Channels & Residential Domicile</h3>
              <p className="text-xs text-slate-400">Used for OTP relay notifications and communication address mapping across forms.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                    <span>Mobile Number</span>
                    {isMobileValid && (
                      <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                        <Check className="w-3 h-3" /> 10-digit format
                      </span>
                    )}
                  </label>
                  {vault.mobile && (
                    <button
                      type="button"
                      onClick={() => copyToClipboard('mobile', vault.mobile)}
                      className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1 font-mono"
                    >
                      {copiedKey === 'mobile' ? <CheckCheck className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedKey === 'mobile' ? 'Copied' : 'Copy'}</span>
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  maxLength={10}
                  value={vault.mobile || ''}
                  onChange={(e) => setVault({ ...vault, mobile: e.target.value })}
                  placeholder="9876543210"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                    <span>Email Address</span>
                    {isEmailValid && (
                      <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                        <Check className="w-3 h-3" /> Valid email
                      </span>
                    )}
                  </label>
                  {vault.email && (
                    <button
                      type="button"
                      onClick={() => copyToClipboard('email', vault.email)}
                      className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1 font-mono"
                    >
                      {copiedKey === 'email' ? <CheckCheck className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedKey === 'email' ? 'Copied' : 'Copy'}</span>
                    </button>
                  )}
                </div>
                <input
                  type="email"
                  value={vault.email || ''}
                  onChange={(e) => setVault({ ...vault, email: e.target.value, confirm_email: e.target.value })}
                  placeholder="candidate@example.com"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div className="md:col-span-2">
                <label className="text-slate-300 font-semibold block mb-1.5">Permanent Address Line 1</label>
                <input
                  type="text"
                  value={vault.address_line_1 || ''}
                  onChange={(e) => setVault({ ...vault, address_line_1: e.target.value })}
                  placeholder="House No, Street / Colony, Village or Town"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">District</label>
                <input
                  type="text"
                  value={vault.district || ''}
                  onChange={(e) => setVault({ ...vault, district: e.target.value })}
                  placeholder="District name"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">State</label>
                <input
                  type="text"
                  value={vault.state || ''}
                  onChange={(e) => setVault({ ...vault, state: e.target.value })}
                  placeholder="State name"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1.5">Pincode (6 digits)</label>
                <input
                  type="text"
                  maxLength={6}
                  value={vault.pincode || ''}
                  onChange={(e) => setVault({ ...vault, pincode: e.target.value })}
                  placeholder="110001"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                />
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Education Records */}
        {activeTab === 'academic' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="border-b border-white/[0.06] pb-3">
              <h3 className="text-sm font-bold text-white">Academic Qualifications & Board Credentials</h3>
              <p className="text-xs text-slate-400">Critical for 10th/12th grade eligibility gates, roll number lookups, and passing marks validation.</p>
            </div>

            {/* Matriculation / 10th Grade */}
            <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/[0.08] space-y-4">
              <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
                <span className="font-bold text-amber-300 flex items-center gap-2 text-xs">
                  <GraduationCap className="w-4 h-4" />
                  Matriculation / Class 10th (Secondary)
                </span>
                <span className="text-[10px] font-mono text-slate-400 uppercase">Standard Baseline</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Board / Authority</label>
                  <input
                    type="text"
                    value={vault.matric?.board || ''}
                    onChange={(e) => setVault({ ...vault, matric: { ...(vault.matric || {}), board: e.target.value } })}
                    placeholder="CBSE / ICSE / State Board"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white outline-none focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Roll Number</label>
                  <input
                    type="text"
                    value={vault.matric?.roll_number || ''}
                    onChange={(e) => setVault({ ...vault, matric: { ...(vault.matric || {}), roll_number: e.target.value } })}
                    placeholder="Roll Number"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Year of Passing</label>
                  <input
                    type="text"
                    maxLength={4}
                    value={vault.matric?.year_of_passing || ''}
                    onChange={(e) => setVault({ ...vault, matric: { ...(vault.matric || {}), year_of_passing: e.target.value } })}
                    placeholder="2018"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Percentage / CGPA</label>
                  <input
                    type="text"
                    value={vault.matric?.percentage || ''}
                    onChange={(e) => setVault({ ...vault, matric: { ...(vault.matric || {}), percentage: e.target.value } })}
                    placeholder="85.4"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                  />
                </div>
              </div>
            </div>

            {/* Intermediate / 12th Grade */}
            <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/[0.08] space-y-4">
              <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
                <span className="font-bold text-sky-300 flex items-center gap-2 text-xs">
                  <GraduationCap className="w-4 h-4" />
                  Intermediate / Class 12th (Higher Secondary)
                </span>
                <span className="text-[10px] font-mono text-slate-400 uppercase">Optional / Higher</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Board / Authority</label>
                  <input
                    type="text"
                    value={vault.intermediate?.board || ''}
                    onChange={(e) => setVault({ ...vault, intermediate: { ...(vault.intermediate || {}), board: e.target.value } })}
                    placeholder="CBSE / State Board"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white outline-none focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Roll Number</label>
                  <input
                    type="text"
                    value={vault.intermediate?.roll_number || ''}
                    onChange={(e) => setVault({ ...vault, intermediate: { ...(vault.intermediate || {}), roll_number: e.target.value } })}
                    placeholder="Roll Number"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Year of Passing</label>
                  <input
                    type="text"
                    maxLength={4}
                    value={vault.intermediate?.year_of_passing || ''}
                    onChange={(e) => setVault({ ...vault, intermediate: { ...(vault.intermediate || {}), year_of_passing: e.target.value } })}
                    placeholder="2020"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Percentage / CGPA</label>
                  <input
                    type="text"
                    value={vault.intermediate?.percentage || ''}
                    onChange={(e) => setVault({ ...vault, intermediate: { ...(vault.intermediate || {}), percentage: e.target.value } })}
                    placeholder="88.2"
                    className="w-full px-3 py-2 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono outline-none focus:border-indigo-400"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Extended Custom Parameters */}
        {activeTab === 'custom' && (
          <div className="glass-panel p-6 rounded-3xl border border-white/[0.08] space-y-5 animate-fadeIn">
            <div className="border-b border-white/[0.06] pb-3">
              <h3 className="text-sm font-bold text-white">Custom Portal Parameters & Extended Facts</h3>
              <p className="text-xs text-slate-400">Define custom field keys matching specific exams (e.g. GATE registration number, NCC certificate, sports quota details).</p>
            </div>

            {/* Existing custom fields */}
            <div className="space-y-3">
              {Object.entries(vault.custom_fields || {}).length === 0 ? (
                <div className="p-6 rounded-2xl bg-white/[0.02] border border-white/[0.06] text-center text-xs text-slate-500 font-mono">
                  No custom parameters defined yet. Add portal-specific attributes below.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(vault.custom_fields || {}).map(([k, v]) => (
                    <div key={k} className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/[0.08] flex items-center justify-between gap-3 text-xs">
                      <div className="min-w-0">
                        <span className="font-mono text-indigo-300 font-bold block truncate">{k}</span>
                        <span className="text-slate-300 truncate block mt-0.5">{String(v)}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDeleteCustomField(k)}
                        className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
                        title="Delete parameter"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Add parameter input group */}
            <div className="p-4 rounded-2xl bg-slate-950/80 border border-white/[0.1] flex flex-wrap items-center gap-3">
              <input
                type="text"
                placeholder="Parameter key (e.g. gate_score)"
                value={newCustomKey}
                onChange={(e) => setNewCustomKey(e.target.value)}
                className="flex-1 min-w-[180px] px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-xs text-white outline-none focus:border-indigo-400 font-mono"
              />
              <input
                type="text"
                placeholder="Parameter value (e.g. 742)"
                value={newCustomVal}
                onChange={(e) => setNewCustomVal(e.target.value)}
                className="flex-1 min-w-[180px] px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-xs text-white outline-none focus:border-indigo-400"
              />
              <button
                type="button"
                onClick={handleAddCustomField}
                disabled={!newCustomKey.trim() || !newCustomVal.trim()}
                className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-xs font-bold text-white flex items-center gap-1.5 transition-colors"
              >
                <Plus className="w-4 h-4" />
                <span>Add Field</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Sticky Bottom Save Action Bar */}
      <div className="sticky bottom-0 p-4 border-t border-white/[0.08] bg-slate-950/90 backdrop-blur-xl mt-auto z-20">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>Changes will be encrypted in local SQLite/JSON vault with zero third-party exposure.</span>
          </div>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className={`px-5 py-2.5 rounded-xl text-xs font-bold flex items-center gap-2 transition-all shadow-md ${
              saveSuccess
                ? 'bg-emerald-600 text-white border border-emerald-500'
                : 'bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-400/40 shadow-indigo-500/20'
            }`}
          >
            {saveSuccess ? (
              <>
                <Check className="w-4 h-4" />
                <span>Profile Saved!</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>{saving ? 'Encrypting & Saving...' : 'Save Profile Changes'}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
