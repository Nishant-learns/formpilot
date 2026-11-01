import React, { useState, useEffect, useRef } from 'react';
import {
  X,
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
} from 'lucide-react';
import { SecurityShieldIcon, BiometricFingerprintIcon } from './CustomIcons';

export default function OneVaultDrawer(props) {
  if (!props.isOpen) return null;
  return <VaultContent {...props} />;
}

function VaultContent({ onClose }) {
  const [vault, setVault] = useState(null);
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
        setTimeout(() => setSaveSuccess(false), 2200);
      }
    } catch (err) {
      console.error('Error saving vault:', err);
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
          alert('Vault profile imported into memory! Click "Save details" to commit to disk.');
        }
      } catch (err) {
        alert('Could not parse JSON file. Please check format.');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleAddCustomField = () => {
    if (!newCustomKey.trim() || !newCustomVal.trim()) return;
    setVault({
      ...vault,
      custom_fields: {
        ...vault.custom_fields,
        [newCustomKey.trim().toLowerCase().replace(/\s+/g, '_')]: newCustomVal.trim(),
      },
    });
    setNewCustomKey('');
    setNewCustomVal('');
  };

  // Validation helpers
  const isAadhaarValid = vault?.aadhaar_number && /^\d{12}$/.test(vault.aadhaar_number.replace(/\s+/g, ''));
  const isMobileValid = vault?.mobile && /^\d{10}$/.test(vault.mobile.replace(/\D/g, ''));
  const isEmailValid = vault?.email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(vault.email);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-[#07090e]/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-2xl glass-panel-elevated specular-top border-l border-white/[0.12] h-full flex flex-col shadow-2xl">
        
        {/* Drawer Header */}
        <div className="px-6 py-4 bg-white/[0.02] border-b border-white/[0.08] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-emerald-500/20 to-teal-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-300 shadow-inner">
              <SecurityShieldIcon className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-extrabold text-white">OneVault Identity</h2>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 uppercase tracking-wider">
                  Local-Only AES
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Zero cloud leaks. Cryptographically bound to your machine for high-speed auto-fill.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleReset}
              className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 text-xs flex items-center gap-1 border border-white/[0.08] transition-colors"
              title="Reset to official demo profile"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors"
              title="Close drawer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex px-6 pt-3 border-b border-white/[0.08] bg-transparent gap-4 text-xs font-semibold shrink-0">
          {[
            { id: 'personal', label: '1. Personal', icon: <User className="w-3.5 h-3.5" /> },
            { id: 'contact', label: '2. Contact & Address', icon: <Phone className="w-3.5 h-3.5" /> },
            { id: 'academic', label: '3. Education', icon: <GraduationCap className="w-3.5 h-3.5" /> },
            { id: 'custom', label: '4. Extended Facts', icon: <Sparkles className="w-3.5 h-3.5" /> },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 flex items-center gap-1.5 border-b-2 transition-all ${
                activeTab === tab.id
                  ? 'border-indigo-400 text-indigo-200'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Form Body */}
        {vault && (
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            
            {/* TAB 1: PERSONAL */}
            {activeTab === 'personal' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-slate-300 font-semibold">Full Name</label>
                    {vault.full_name && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard('full_name', vault.full_name)}
                        className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1"
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
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Father's Name</label>
                  <input
                    type="text"
                    value={vault.father_name || ''}
                    onChange={(e) => setVault({ ...vault, father_name: e.target.value, verify_father_name: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Mother's Name</label>
                  <input
                    type="text"
                    value={vault.mother_name || ''}
                    onChange={(e) => setVault({ ...vault, mother_name: e.target.value, verify_mother_name: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Date of Birth (YYYY-MM-DD)</label>
                  <input
                    type="date"
                    value={vault.dob || ''}
                    onChange={(e) => setVault({ ...vault, dob: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Gender</label>
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
                  <label className="text-slate-300 font-semibold block mb-1">Social Category</label>
                  <select
                    value={vault.category || 'UR'}
                    onChange={(e) => setVault({ ...vault, category: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  >
                    <option value="UR">UR (General)</option>
                    <option value="EWS">EWS</option>
                    <option value="OBC-NCL">OBC-NCL</option>
                    <option value="SC">SC</option>
                    <option value="ST">ST</option>
                  </select>
                </div>

                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Domicile State</label>
                  <input
                    type="text"
                    value={vault.domicile_state || ''}
                    onChange={(e) => setVault({ ...vault, domicile_state: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                      <span>Aadhaar Number</span>
                      {isAadhaarValid ? (
                        <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                          <Check className="w-3 h-3" /> valid 12-digit
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500 font-mono">(12 digits)</span>
                      )}
                    </label>
                    {vault.aadhaar_number && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard('aadhaar', vault.aadhaar_number)}
                        className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1"
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

                <div className="md:col-span-2">
                  <label className="text-slate-300 font-semibold block mb-1">Visible Identification Mark</label>
                  <input
                    type="text"
                    value={vault.identification_mark_1 || ''}
                    onChange={(e) => setVault({ ...vault, identification_mark_1: e.target.value })}
                    placeholder="e.g. Mole on right cheek / Scar on forehead"
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>
              </div>
            )}

            {/* TAB 2: CONTACT & ADDRESS */}
            {activeTab === 'contact' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                      <span>Mobile Number</span>
                      {isMobileValid && (
                        <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                          <Check className="w-3 h-3" /> 10-digit
                        </span>
                      )}
                    </label>
                    {vault.mobile && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard('mobile', vault.mobile)}
                        className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1"
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
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                      <span>Email ID</span>
                      {isEmailValid && (
                        <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-0.5">
                          <Check className="w-3 h-3" /> valid
                        </span>
                      )}
                    </label>
                    {vault.email && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard('email', vault.email)}
                        className="text-[10px] text-slate-500 hover:text-indigo-300 flex items-center gap-1"
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
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="text-slate-300 font-semibold block mb-1">Permanent Address Line 1</label>
                  <input
                    type="text"
                    value={vault.address_line_1 || ''}
                    onChange={(e) => setVault({ ...vault, address_line_1: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="text-slate-300 font-semibold block mb-1">District</label>
                  <input
                    type="text"
                    value={vault.district || ''}
                    onChange={(e) => setVault({ ...vault, district: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>

                <div>
                  <label className="text-slate-300 font-semibold block mb-1">Pincode (6 digits)</label>
                  <input
                    type="text"
                    maxLength={6}
                    value={vault.pincode || ''}
                    onChange={(e) => setVault({ ...vault, pincode: e.target.value })}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950/80 border border-white/[0.1] text-white font-mono font-medium focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 outline-none transition-all"
                  />
                </div>
              </div>
            )}

            {/* TAB 3: ACADEMIC PARTICULARS */}
            {activeTab === 'academic' && (
              <div className="space-y-4 text-xs">
                <div className="p-4 bg-slate-950/80 rounded-2xl border border-white/[0.1] shadow-inner">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="font-bold text-amber-300 flex items-center gap-1.5">
                      <GraduationCap className="w-4 h-4" />
                      <span>Class 10th / Matriculation Records</span>
                    </h4>
                    {vault.matric?.roll_number && (
                      <button
                        type="button"
                        onClick={() => copyToClipboard('roll_number', vault.matric.roll_number)}
                        className="text-[10px] text-slate-500 hover:text-amber-300 flex items-center gap-1"
                      >
                        {copiedKey === 'roll_number' ? <CheckCheck className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                        <span>{copiedKey === 'roll_number' ? 'Copied Roll No' : 'Copy Roll No'}</span>
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="text-slate-400 block mb-1">Education Board</label>
                      <input
                        type="text"
                        value={vault.matric?.board || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, board: e.target.value } })}
                        placeholder="e.g. CBSE / ICSE / State Board"
                        className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/[0.08] text-white font-medium focus:border-amber-400 outline-none transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 block mb-1">Roll Number</label>
                      <input
                        type="text"
                        value={vault.matric?.roll_number || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, roll_number: e.target.value } })}
                        className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/[0.08] text-white font-mono font-medium focus:border-amber-400 outline-none transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 block mb-1">Passing Year</label>
                      <input
                        type="text"
                        maxLength={4}
                        value={vault.matric?.passing_year || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, passing_year: e.target.value } })}
                        placeholder="e.g. 2021"
                        className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/[0.08] text-white font-mono font-medium focus:border-amber-400 outline-none transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 block mb-1">Aggregate Marks / Percentage (%)</label>
                      <input
                        type="text"
                        value={vault.matric?.percentage || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, percentage: e.target.value } })}
                        placeholder="e.g. 88.5%"
                        className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-white/[0.08] text-white font-mono font-medium focus:border-amber-400 outline-none transition-all"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: EXTENSIBLE CUSTOM FIELDS */}
            {activeTab === 'custom' && (
              <div className="space-y-4 text-xs">
                <div className="p-3.5 bg-amber-500/10 border border-amber-500/25 rounded-2xl text-amber-200 leading-relaxed">
                  Store custom agency facts such as APAAR ID, DigiLocker ID, typing speed (WPM), or height measurement. FormPilot matches them dynamically to unfamiliar fields.
                </div>

                <div className="space-y-2">
                  {Object.entries(vault.custom_fields || {}).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2.5 p-3 rounded-xl bg-slate-950/80 border border-white/[0.08]">
                      <span className="font-mono text-amber-300 font-bold w-1/3 truncate">{k}</span>
                      <input
                        type="text"
                        value={v}
                        onChange={(e) => setVault({
                          ...vault,
                          custom_fields: { ...vault.custom_fields, [k]: e.target.value },
                        })}
                        className="flex-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-white/[0.08] text-white font-medium focus:border-amber-400 outline-none transition-all"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const updated = { ...vault.custom_fields };
                          delete updated[k];
                          setVault({ ...vault, custom_fields: updated });
                        }}
                        className="p-1 rounded-md text-slate-500 hover:text-red-400 transition-colors"
                        title="Delete field"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>

                {/* Add New Custom Field */}
                <div className="p-4 rounded-2xl bg-slate-950/80 border border-white/[0.08] space-y-2.5">
                  <span className="font-bold text-slate-200 block">Add Extended Field:</span>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Identifier key (e.g. apaar_id)"
                      value={newCustomKey}
                      onChange={(e) => setNewCustomKey(e.target.value)}
                      className="w-1/2 px-3 py-2 rounded-xl bg-slate-900 border border-white/[0.08] text-white font-mono text-xs focus:border-amber-400 outline-none transition-all"
                    />
                    <input
                      type="text"
                      placeholder="Value"
                      value={newCustomVal}
                      onChange={(e) => setNewCustomVal(e.target.value)}
                      className="w-1/2 px-3 py-2 rounded-xl bg-slate-900 border border-white/[0.08] text-white text-xs focus:border-amber-400 outline-none transition-all"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleAddCustomField}
                    className="px-3.5 py-1.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-slate-200 font-semibold text-xs border border-white/[0.1] transition-all"
                  >
                    + Add Field
                  </button>
                </div>
              </div>
            )}

          </div>
        )}

        {/* Drawer Footer */}
        <div className="px-6 py-4 bg-white/[0.02] border-t border-white/[0.08] flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportJson}
              className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 border border-white/[0.08] text-xs font-semibold flex items-center gap-1.5 transition-colors"
              title="Backup vault to a JSON file"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export JSON</span>
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 border border-white/[0.08] text-xs font-semibold flex items-center gap-1.5 transition-colors"
              title="Restore vault from a backup JSON"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Import JSON</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleImportJson}
              className="hidden"
            />
          </div>

          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-400 hover:to-violet-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-lg shadow-indigo-500/20 disabled:opacity-50 transition-all"
          >
            {saveSuccess ? (
              <>
                <Check className="w-4 h-4 text-emerald-300" />
                <span>Saved securely!</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>{saving ? 'Saving...' : 'Save details'}</span>
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}
