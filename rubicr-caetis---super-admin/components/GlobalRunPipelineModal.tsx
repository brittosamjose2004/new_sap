import React, { useState } from 'react';
import { X, Play, Check, Database, Calendar, Building2, Search } from 'lucide-react';
import { CompanySummary } from '../types';

interface GlobalRunPipelineModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStart: (config: { dataSources: string[]; financialYears: string[]; companyIds: string[] }) => void;
  companies: CompanySummary[];
}

const GlobalRunPipelineModal: React.FC<GlobalRunPipelineModalProps> = ({ isOpen, onClose, onStart, companies }) => {
  const [selectedSources, setSelectedSources] = useState<string[]>(['Secondary']);
  const [selectedYears, setSelectedYears] = useState<string[]>(['FY2024']);
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<string[]>([]);
  const [companySearch, setCompanySearch] = useState('');

  if (!isOpen) return null;

  const dataSources = ['Secondary', 'Tertiary'];
  
  // Generate last 50 financial years
  const currentYear = new Date().getFullYear();
  const financialYears = Array.from({ length: 50 }, (_, i) => `FY${currentYear - i}`);

  const filteredCompanies = companies.filter(c => 
    c.name.toLowerCase().includes(companySearch.toLowerCase()) ||
    c.ticker.toLowerCase().includes(companySearch.toLowerCase())
  );

  const toggleSource = (source: string) => {
    setSelectedSources(prev => 
      prev.includes(source) ? prev.filter(s => s !== source) : [...prev, source]
    );
  };

  const toggleYear = (year: string) => {
    setSelectedYears(prev => 
      prev.includes(year) ? prev.filter(y => y !== year) : [...prev, year]
    );
  };

  const toggleCompany = (id: string) => {
    setSelectedCompanyIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const toggleAllCompanies = () => {
    if (selectedCompanyIds.length === companies.length) {
      setSelectedCompanyIds([]);
    } else {
      setSelectedCompanyIds(companies.map(c => c.id));
    }
  };

  const handleStart = () => {
    onStart({ 
      dataSources: selectedSources, 
      financialYears: selectedYears, 
      companyIds: selectedCompanyIds 
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-md transition-opacity"
        onClick={onClose}
      />

      {/* Modal Panel */}
      <div className="w-full max-w-3xl bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden relative flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-8 py-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-600/20 rounded-xl flex items-center justify-center">
              <Play className="w-5 h-5 text-indigo-400 fill-current" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight">Global Pipeline Run</h2>
              <p className="text-slate-500 text-xs mt-0.5 uppercase tracking-widest font-bold">Bulk Processing Configuration</p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-2 hover:bg-slate-800 rounded-full text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-8 space-y-10">
          
          {/* Section 1: Data Sources */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Database className="w-4 h-4 text-indigo-400" />
              <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Data Sources</h3>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {dataSources.map(source => (
                <button
                  key={source}
                  onClick={() => toggleSource(source)}
                  className={`
                    flex items-center justify-between p-4 rounded-2xl border transition-all
                    ${selectedSources.includes(source) 
                      ? 'bg-indigo-500/10 border-indigo-500 text-indigo-400 shadow-lg shadow-indigo-500/5' 
                      : 'bg-slate-950 border-slate-800 text-slate-500 hover:border-slate-700 hover:text-slate-300'}
                  `}
                >
                  <span className="font-semibold">{source} Data</span>
                  <div className={`
                    w-6 h-6 rounded-full border flex items-center justify-center transition-all
                    ${selectedSources.includes(source) ? 'bg-indigo-500 border-indigo-500' : 'border-slate-700'}
                  `}>
                    {selectedSources.includes(source) && <Check className="w-4 h-4 text-white" />}
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Section 2: Companies */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Target Companies</h3>
              </div>
              <div className="flex items-center gap-3">
                <button 
                  onClick={toggleAllCompanies}
                  className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 uppercase tracking-wider"
                >
                  {selectedCompanyIds.length === companies.length ? 'Deselect All' : 'Select All'}
                </button>
                <span className="text-[10px] font-bold text-slate-500 bg-slate-800 px-2 py-1 rounded uppercase">
                  {selectedCompanyIds.length} Selected
                </span>
              </div>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden">
              <div className="p-3 border-b border-slate-800 flex items-center gap-2">
                <Search className="w-4 h-4 text-slate-500" />
                <input 
                  type="text"
                  placeholder="Filter companies..."
                  value={companySearch}
                  onChange={(e) => setCompanySearch(e.target.value)}
                  className="bg-transparent border-none focus:outline-none text-sm text-slate-200 w-full"
                />
              </div>
              <div className="max-h-48 overflow-y-auto p-2 grid grid-cols-2 gap-2">
                {filteredCompanies.map(company => (
                  <button
                    key={company.id}
                    onClick={() => toggleCompany(company.id)}
                    className={`
                      flex items-center gap-3 p-2 rounded-xl border transition-all text-left
                      ${selectedCompanyIds.includes(company.id) 
                        ? 'bg-indigo-500/10 border-indigo-500/50 text-indigo-300' 
                        : 'bg-slate-900 border-slate-800 text-slate-500 hover:border-slate-700 hover:text-slate-400'}
                    `}
                  >
                    <div className={`
                      w-4 h-4 rounded border flex items-center justify-center shrink-0
                      ${selectedCompanyIds.includes(company.id) ? 'bg-indigo-500 border-indigo-500' : 'border-slate-700'}
                    `}>
                      {selectedCompanyIds.includes(company.id) && <Check className="w-3 h-3 text-white" />}
                    </div>
                    <div className="truncate">
                      <p className="text-xs font-bold truncate">{company.name}</p>
                      <p className="text-[10px] opacity-60">{company.ticker}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Section 3: Financial Years */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider">Financial Years</h3>
              </div>
              <span className="text-[10px] font-bold text-slate-500 bg-slate-800 px-2 py-1 rounded uppercase">
                {selectedYears.length} Selected
              </span>
            </div>
            <div className="grid grid-cols-4 sm:grid-cols-6 gap-2 bg-slate-950 p-4 rounded-2xl border border-slate-800">
              {financialYears.map(year => (
                <button
                  key={year}
                  onClick={() => toggleYear(year)}
                  className={`
                    py-2 rounded-lg text-[10px] font-mono transition-all border
                    ${selectedYears.includes(year) 
                      ? 'bg-indigo-500 text-white border-indigo-500 shadow-lg shadow-indigo-500/20' 
                      : 'bg-slate-900 text-slate-500 border-slate-800 hover:border-slate-700 hover:text-slate-300'}
                  `}
                >
                  {year}
                </button>
              ))}
            </div>
          </section>

        </div>

        {/* Footer */}
        <div className="p-8 border-t border-slate-800 bg-slate-900/50 backdrop-blur-md sticky bottom-0 z-10 flex gap-4">
          <button 
            onClick={onClose}
            className="flex-1 px-6 py-4 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-2xl font-bold transition-all"
          >
            Cancel
          </button>
          <button 
            onClick={handleStart}
            disabled={selectedSources.length === 0 || selectedYears.length === 0 || selectedCompanyIds.length === 0}
            className="flex-[2] px-6 py-4 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-2xl font-bold shadow-xl shadow-indigo-500/20 flex items-center justify-center gap-2 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            Start Global Pipeline <ArrowRight className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

const ArrowRight = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
  </svg>
);

export default GlobalRunPipelineModal;
