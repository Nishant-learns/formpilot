import React, { useState, useEffect } from 'react';
import { X, Save, RotateCcw, User, Phone, GraduationCap, Sparkles, Check, Download, Upload } from 'lucide-react';

export default function OneVaultDrawer({ isOpen, onClose }) {
  if (!isOpen) return null;

  const [vault, setVault] = useState(null);
  const [activeTab, setActiveTab] = useState('personal');
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [newCustomKey, setNewCustomKey] = useState('');
  const [newCustomVal, setNewCustomVal] = useState('');

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
        setTimeout(() => setSaveSuccess(false), 2000);
      }
    } catch (err) {
      console.error('Error saving vault:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Reset One-Vault to high-fidelity default profile?')) return;
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

  const handleAddCustomField = () => {
    if (!newCustomKey.trim() || !newCustomVal.trim()) return;
    setVault({
      ...vault,
      custom_fields: {
        ...vault.custom_fields,
        [newCustomKey.trim().toLowerCase().replace(/\s+/g, '_')]: newCustomVal.trim()
      }
    });
    setNewCustomKey('');
    setNewCustomVal('');
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/70 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-2xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl">
        
        {/* Drawer Header */}
        <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-base font-extrabold text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <span>Persistent Candidate One-Vault</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Verified single-source of truth for millions of government forms
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs flex items-center gap-1 border border-slate-700"
              title="Reset to default candidate"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex px-6 pt-3 border-b border-slate-800 bg-slate-950/50 gap-4 text-xs font-semibold">
          {[
            { id: 'personal', label: '1. Personal & Caste', icon: <User className="w-3.5 h-3.5" /> },
            { id: 'contact', label: '2. Contact & Address', icon: <Phone className="w-3.5 h-3.5" /> },
            { id: 'academic', label: '3. Academic Records', icon: <GraduationCap className="w-3.5 h-3.5" /> },
            { id: 'custom', label: '4. Dynamic Custom IDs', icon: <Sparkles className="w-3.5 h-3.5" /> },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 flex items-center gap-1.5 border-b-2 transition-all ${
                activeTab === tab.id
                  ? 'border-amber-400 text-amber-300'
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
            
            {/* TAB 1: PERSONAL & CASTE */}
            {activeTab === 'personal' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Full Name</label>
                  <input
                    type="text"
                    value={vault.full_name || ''}
                    onChange={(e) => setVault({ ...vault, full_name: e.target.value, verify_full_name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Father's Name</label>
                  <input
                    type="text"
                    value={vault.father_name || ''}
                    onChange={(e) => setVault({ ...vault, father_name: e.target.value, verify_father_name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Mother's Name</label>
                  <input
                    type="text"
                    value={vault.mother_name || ''}
                    onChange={(e) => setVault({ ...vault, mother_name: e.target.value, verify_mother_name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Date of Birth (YYYY-MM-DD)</label>
                  <input
                    type="date"
                    value={vault.dob || ''}
                    onChange={(e) => setVault({ ...vault, dob: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Gender</label>
                  <select
                    value={vault.gender || 'Male'}
                    onChange={(e) => setVault({ ...vault, gender: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  >
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                    <option value="Transgender">Transgender</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Social Category</label>
                  <select
                    value={vault.category || 'UR'}
                    onChange={(e) => setVault({ ...vault, category: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  >
                    <option value="UR">UR (General)</option>
                    <option value="EWS">EWS</option>
                    <option value="OBC-NCL">OBC-NCL</option>
                    <option value="SC">SC</option>
                    <option value="ST">ST</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Domicile State</label>
                  <input
                    type="text"
                    value={vault.domicile_state || ''}
                    onChange={(e) => setVault({ ...vault, domicile_state: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Aadhaar Card (12 Digits)</label>
                  <input
                    type="text"
                    value={vault.aadhaar_number || ''}
                    onChange={(e) => setVault({ ...vault, aadhaar_number: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="text-slate-400 font-semibold block mb-1">Identification Mark 1</label>
                  <input
                    type="text"
                    value={vault.identification_mark_1 || ''}
                    onChange={(e) => setVault({ ...vault, identification_mark_1: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
              </div>
            )}

            {/* TAB 2: CONTACT & ADDRESS */}
            {activeTab === 'contact' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Mobile Number</label>
                  <input
                    type="text"
                    value={vault.mobile || ''}
                    onChange={(e) => setVault({ ...vault, mobile: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Email ID</label>
                  <input
                    type="email"
                    value={vault.email || ''}
                    onChange={(e) => setVault({ ...vault, email: e.target.value, confirm_email: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="text-slate-400 font-semibold block mb-1">Permanent Address Line 1</label>
                  <input
                    type="text"
                    value={vault.address_line_1 || ''}
                    onChange={(e) => setVault({ ...vault, address_line_1: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">District</label>
                  <input
                    type="text"
                    value={vault.district || ''}
                    onChange={(e) => setVault({ ...vault, district: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
                <div>
                  <label className="text-slate-400 font-semibold block mb-1">Pincode</label>
                  <input
                    type="text"
                    value={vault.pincode || ''}
                    onChange={(e) => setVault({ ...vault, pincode: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-white font-medium"
                  />
                </div>
              </div>
            )}

            {/* TAB 3: ACADEMIC PARTICULARS */}
            {activeTab === 'academic' && (
              <div className="space-y-4 text-xs">
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
                  <h4 className="font-bold text-amber-400 mb-2">Class 10th / Matriculation</h4>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-slate-400 block mb-1">Board</label>
                      <input
                        type="text"
                        value={vault.matric?.board || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, board: e.target.value } })}
                        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-white font-medium"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 block mb-1">Roll Number</label>
                      <input
                        type="text"
                        value={vault.matric?.roll_number || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, roll_number: e.target.value } })}
                        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-white font-medium"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 block mb-1">Passing Year</label>
                      <input
                        type="text"
                        value={vault.matric?.passing_year || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, passing_year: e.target.value } })}
                        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-white font-medium"
                      />
                    </div>
                    <div>
                      <label className="text-slate-400 block mb-1">Percentage (%)</label>
                      <input
                        type="text"
                        value={vault.matric?.percentage || ''}
                        onChange={(e) => setVault({ ...vault, matric: { ...vault.matric, percentage: e.target.value } })}
                        className="w-full px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-white font-medium"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: EXTENSIBLE CUSTOM FIELDS */}
            {activeTab === 'custom' && (
              <div className="space-y-4 text-xs">
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300">
                  Dynamic fields automatically captured when government portals demand custom IDs (e.g. APAAR ID, DigiLocker ID, Height, Chest, etc.).
                </div>

                <div className="space-y-2">
                  {Object.entries(vault.custom_fields || {}).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                      <span className="font-mono text-amber-400 font-bold w-1/3 truncate">{k}</span>
                      <input
                        type="text"
                        value={v}
                        onChange={(e) => setVault({
                          ...vault,
                          custom_fields: { ...vault.custom_fields, [k]: e.target.value }
                        })}
                        className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-white font-medium"
                      />
                    </div>
                  ))}
                </div>

                {/* Add New Custom Field */}
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <span className="font-bold text-slate-300 block">Add New Extensible Field:</span>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Field Name (e.g. typing_wpm)"
                      value={newCustomKey}
                      onChange={(e) => setNewCustomKey(e.target.value)}
                      className="w-1/2 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-white font-medium"
                    />
                    <input
                      type="text"
                      placeholder="Value"
                      value={newCustomVal}
                      onChange={(e) => setNewCustomVal(e.target.value)}
                      className="w-1/2 px-3 py-1.5 rounded bg-slate-900 border border-slate-700 text-white font-medium"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleAddCustomField}
                    className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs border border-slate-700"
                  >
                    + Add Field
                  </button>
                </div>
              </div>
            )}

          </div>
        )}

        {/* Drawer Footer */}
        <div className="px-6 py-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between shrink-0">
          <span className="text-xs text-slate-500 font-mono">
            Encrypted JSON Vault on Disk
          </span>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-extrabold text-xs flex items-center gap-1.5 shadow-lg shadow-amber-500/20 disabled:opacity-50"
          >
            {saveSuccess ? (
              <>
                <Check className="w-4 h-4 text-emerald-950" />
                <span>Saved Permanently!</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>{saving ? 'Saving...' : 'Save to One-Vault'}</span>
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}
