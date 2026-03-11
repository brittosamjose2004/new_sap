import React, { useState } from 'react';
import { Search, Globe, CheckCircle2, AlertCircle, ArrowRight, Loader2, X, Building, ExternalLink, PenLine } from 'lucide-react';

interface AddCompanyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (companyData: any) => void;
}

// Steps: 0: Search, 'manual': Manual Entry, 1: Confirm, 2: Config, 3: Success/Trigger
type Step = 0 | 'manual' | 1 | 2 | 3;

const AddCompanyModal: React.FC<AddCompanyModalProps> = ({ isOpen, onClose, onAdd }) => {
  const [step, setStep] = useState<Step>(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<any>(null);
  
  // Config state
  const [selectedRegion, setSelectedRegion] = useState('NA');
  const [selectedSector, setSelectedSector] = useState('Technology');
  const [error, setError] = useState<string | null>(null);
  const [totalResults, setTotalResults] = useState<number>(0);

  // Manual entry state
  const [manualName, setManualName] = useState('');
  const [manualLei, setManualLei] = useState('');
  const [manualAddress, setManualAddress] = useState('');
  const [manualJurisdiction, setManualJurisdiction] = useState('');

  if (!isOpen) return null;

  // Map country code → region
  const _countryToRegion = (code: string): string => {
    const c = code.toUpperCase();
    if (['US','CA','MX'].includes(c)) return 'NA';
    if (['GB','DE','FR','NL','ES','IT','SE','CH','BE','NO','DK','FI','PL','PT','AT','IE'].includes(c)) return 'EU';
    if (['IN','CN','JP','AU','SG','HK','KR','MY','TH','ID','NZ','PH'].includes(c)) return 'APAC';
    if (['BR','AR','CL','CO','PE'].includes(c)) return 'LATAM';
    return 'EMEA';
  };
  void _countryToRegion; // used server-side

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    setError(null);
    setSearchResults([]);
    setTotalResults(0);

    try {
      const q = encodeURIComponent(searchQuery.trim());
      const res = await fetch(`/api/search/companies?q=${q}&per_page=10`);
      if (!res.ok) throw new Error(`OpenCorporates returned ${res.status}`);
      const data = await res.json();
      const companies = data?.results?.companies ?? [];
      setTotalResults(data?.results?.total_count ?? companies.length);

      if (companies.length === 0) {
        setError('no_results');
        return;
      }

      const mapped = companies.map((c: any) => ({
        name: c.name,
        lei: c.lei ?? '',
        address: c.address || '—',
        ticker: c.ticker ?? '',
        region: c.region || 'APAC',
        sector: c.sector || 'Unknown',
        opencorporates_url: '',
        incorporation_date: c.incorporation_date || '',
        company_number: c.company_number || c.lei || '',
        jurisdiction: c.jurisdiction || '',
      }));

      setSearchResults(mapped);
    } catch (err: any) {
      console.error('OpenCorporates search error:', err);
      setError('Failed to search companies. Please check your connection and try again.');
    } finally {
      setIsSearching(false);
    }
  };

  const handleTrigger = () => {
    // Transition to loading/success
    setStep(3);
    // Simulate pipeline start
    setTimeout(() => {
        onAdd({
            name: selectedEntity.name,
            lei: selectedEntity.lei,
            region: selectedRegion,
            sector: selectedSector,
            status: 'QUEUED'
        });
    }, 1500);
  };

  const renderStepContent = () => {
    switch(step) {
      case 0: // Global Search
        return (
          <div className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
              <input 
                type="text" 
                placeholder="Search by Legal Name or LEI..." 
                className="w-full bg-slate-800 border border-slate-700 rounded-lg py-3 pl-10 pr-4 text-slate-200 focus:border-indigo-500 focus:outline-none"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
              <button 
                onClick={handleSearch}
                className="absolute right-2 top-2 bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1 rounded text-sm transition-colors"
              >
                Search
              </button>
            </div>
            
            <div className="min-h-[200px]">
              {isSearching ? (
                <div className="flex flex-col items-center justify-center h-40 text-slate-500">
                  <Loader2 className="w-8 h-8 animate-spin mb-2" />
                  <span className="text-sm">Searching GLEIF LEI Registry...</span>
                </div>
              ) : error === 'no_results' ? (
                <div className="flex flex-col items-center justify-center h-40 text-slate-400 text-center px-4 gap-3">
                  <AlertCircle className="w-8 h-8 text-amber-500" />
                  <div>
                    <p className="text-sm font-medium text-slate-300">No companies found in GLEIF registry</p>
                    <p className="text-xs text-slate-500 mt-1">GLEIF only lists LEI-registered entities. Small or private companies may not appear.</p>
                  </div>
                  <button
                    onClick={() => { setManualName(searchQuery); setStep('manual'); }}
                    className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                  >
                    <PenLine className="w-4 h-4" /> Add Company Manually
                  </button>
                </div>
              ) : error ? (
                <div className="flex flex-col items-center justify-center h-40 text-red-400 text-center px-4">
                  <AlertCircle className="w-8 h-8 mb-2" />
                  <p className="text-sm">{error}</p>
                  <button 
                    onClick={handleSearch}
                    className="mt-2 text-xs text-indigo-400 hover:underline"
                  >
                    Try again
                  </button>
                </div>
              ) : searchResults.length > 0 ? (
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <p className="text-xs text-slate-500 uppercase font-semibold">Found Entities</p>
                      <a href="https://gleif.org" target="_blank" rel="noopener noreferrer" className="text-[10px] text-slate-600 hover:text-indigo-400 flex items-center gap-1 transition-colors">
                      <Globe className="w-2.5 h-2.5" /> Powered by GLEIF LEI Registry
                    </a>
                  </div>
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {searchResults.map((result, idx) => (
                      <div
                        key={idx}
                        onClick={() => {
                          setSelectedEntity(result);
                          setSelectedRegion(result.region || 'NA');
                          setSelectedSector(result.sector || 'Technology');
                          setStep(1);
                        }}
                        className="p-3 bg-slate-800/50 border border-slate-700 hover:border-indigo-500 hover:bg-indigo-500/10 rounded-lg cursor-pointer transition-all flex justify-between items-center group"
                      >
                        <div className="min-w-0">
                          <h4 className="font-medium text-slate-200 group-hover:text-indigo-400 truncate">{result.name}</h4>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            {result.lei && <span className="text-xs font-mono bg-slate-900 px-1 rounded text-slate-400">LEI: {result.lei}</span>}
                            {result.company_number && <span className="text-xs font-mono bg-slate-900 px-1 rounded text-slate-500"># {result.company_number}</span>}
                            <span className="text-xs text-slate-500 truncate">{result.address}</span>
                          </div>
                          {result.incorporation_date && (
                            <p className="text-[10px] text-slate-600 mt-0.5">Inc. {result.incorporation_date} · {result.jurisdiction?.toUpperCase()}</p>
                          )}
                        </div>
                        <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-indigo-400 shrink-0 ml-2" />
                      </div>
                    ))}
                  </div>
                  {totalResults > searchResults.length && (
                    <p className="text-[10px] text-slate-600 text-center">Showing {searchResults.length} of {totalResults.toLocaleString()} results. Try a more specific name.</p>
                  )}
                  <button
                    onClick={() => { setManualName(searchQuery); setStep('manual'); }}
                    className="w-full flex items-center justify-center gap-1.5 text-xs text-slate-500 hover:text-indigo-400 transition-colors border border-dashed border-slate-700 hover:border-indigo-500 px-3 py-2 rounded-lg"
                  >
                    <PenLine className="w-3.5 h-3.5" /> Can't find your company? Add manually
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-40 text-slate-600 gap-3">
                  <Globe className="w-12 h-12 opacity-20" />
                  <p className="text-sm">Search the GLEIF LEI Registry to find & verify legal entities.</p>
                  <button
                    onClick={() => setStep('manual')}
                    className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-indigo-400 transition-colors border border-slate-700 hover:border-indigo-500 px-3 py-1.5 rounded-lg"
                  >
                    <PenLine className="w-3.5 h-3.5" /> Or add company manually
                  </button>
                </div>
              )}
            </div>
          </div>
        );
      
      case 'manual': // Manual Entry
        return (
          <div className="space-y-4">
            <p className="text-xs text-slate-500">Enter the company details manually. The LEI code is optional but recommended for verified entities.</p>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Legal Name <span className="text-red-400">*</span></label>
              <input
                type="text"
                placeholder="e.g. Impactree Data Technologies Private Limited"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg py-2.5 px-3 text-slate-200 focus:border-indigo-500 focus:outline-none text-sm"
                value={manualName}
                onChange={(e) => setManualName(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">LEI Code <span className="text-slate-600">(optional)</span></label>
                <input
                  type="text"
                  placeholder="20-char LEI code"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg py-2.5 px-3 text-slate-200 focus:border-indigo-500 focus:outline-none text-sm font-mono"
                  value={manualLei}
                  onChange={(e) => setManualLei(e.target.value.toUpperCase())}
                  maxLength={20}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Country Code</label>
                <input
                  type="text"
                  placeholder="e.g. IN, US, GB"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg py-2.5 px-3 text-slate-200 focus:border-indigo-500 focus:outline-none text-sm uppercase"
                  value={manualJurisdiction}
                  onChange={(e) => setManualJurisdiction(e.target.value.toUpperCase())}
                  maxLength={2}
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Address <span className="text-slate-600">(optional)</span></label>
              <input
                type="text"
                placeholder="City, Country"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg py-2.5 px-3 text-slate-200 focus:border-indigo-500 focus:outline-none text-sm"
                value={manualAddress}
                onChange={(e) => setManualAddress(e.target.value)}
              />
            </div>
          </div>
        );

      case 1: // Confirmation
        return (
          <div className="space-y-6 text-center py-4">
             <div className="w-16 h-16 bg-indigo-500/20 rounded-full flex items-center justify-center mx-auto text-indigo-400">
                <Building className="w-8 h-8" />
             </div>
             <div>
                <h3 className="text-xl font-semibold text-white">{selectedEntity.name}</h3>
                <p className="text-slate-400 text-sm mt-1">{selectedEntity.address}</p>
                <div className="mt-4 inline-block bg-slate-900 border border-slate-700 rounded px-3 py-1 text-xs font-mono text-slate-300">
                    LEI: {selectedEntity.lei}
                </div>
             </div>
             <p className="text-sm text-slate-400 max-w-sm mx-auto">
                Is this the correct legal entity you wish to ingest? This will trigger a credit check and ESG scrape.
             </p>
          </div>
        );

      case 2: // Configuration
        return (
          <div className="space-y-4">
            <div>
               <label className="block text-xs text-slate-500 uppercase font-semibold mb-2">Primary Operating Region</label>
               <div className="grid grid-cols-2 gap-2">
                  {['NA', 'EU', 'APAC', 'LATAM'].map(region => (
                    <button
                        key={region}
                        onClick={() => setSelectedRegion(region)}
                        className={`p-3 rounded border text-sm font-medium transition-all ${
                            selectedRegion === region 
                            ? 'bg-indigo-600 text-white border-indigo-600' 
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'
                        }`}
                    >
                        {region}
                    </button>
                  ))}
               </div>
            </div>

            <div>
               <label className="block text-xs text-slate-500 uppercase font-semibold mb-2">Sector Classification</label>
               <select 
                  className="w-full bg-slate-800 border border-slate-700 rounded p-3 text-slate-200 focus:border-indigo-500 outline-none appearance-none"
                  value={selectedSector}
                  onChange={(e) => setSelectedSector(e.target.value)}
               >
                   <option>Technology</option>
                   <option>Materials / Steel</option>
                   <option>Energy / Oil & Gas</option>
                   <option>Finance</option>
                   <option>Consumer Goods</option>
               </select>
            </div>

            <div className="bg-amber-500/10 border border-amber-500/20 p-3 rounded flex gap-3 items-start">
               <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
               <p className="text-xs text-amber-200">
                  Selecting the correct region optimizes the scraper for local regulatory filings (e.g., CSRD in EU, SEBI in India).
               </p>
            </div>
          </div>
        );

      case 3: // Processing
         return (
             <div className="flex flex-col items-center justify-center py-10 space-y-4">
                 <Loader2 className="w-12 h-12 text-indigo-500 animate-spin" />
                 <div className="text-center">
                    <h3 className="text-lg font-medium text-white">Initializing Pipeline</h3>
                    <p className="text-slate-400 text-sm">Allocating scrapers and fetching open web data...</p>
                 </div>
             </div>
         );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={onClose} />
      
      {/* Modal Content */}
      <div className="relative bg-slate-900 border border-slate-800 rounded-xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center bg-slate-900">
          <div>
            <h2 className="text-lg font-semibold text-white">Add Company</h2>
            <p className="text-xs text-slate-500">Step {step + 1} of 3</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 flex-1 overflow-y-auto">
          {renderStepContent()}
        </div>

        {/* Footer */}
        {step !== 3 && (
            <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/50 flex justify-between">
                {step !== 0 ? (
                    <button 
                        onClick={() => {
                          if (step === 'manual') setStep(0);
                          else if (step === 1) setStep(selectedEntity?._manual ? 'manual' : 0);
                          else setStep(prev => (prev as number) - 1 as Step);
                        }}
                        className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-white transition-colors"
                    >
                        Back
                    </button>
                ) : <div></div>}
                
                {step === 0 && (
                   <a href="https://gleif.org" target="_blank" rel="noopener noreferrer" className="text-xs text-slate-600 hover:text-indigo-400 flex items-center gap-1 transition-colors">
                      <Globe className="w-3 h-3" /> Powered by GLEIF LEI Registry
                   </a>
                )}

                {step === 'manual' && (
                    <button
                        onClick={() => {
                          if (!manualName.trim()) return;
                          setSelectedEntity({
                            name: manualName.trim(),
                            lei: manualLei.trim(),
                            address: manualAddress.trim() || '—',
                            ticker: '',
                            region: _countryToRegion(manualJurisdiction),
                            sector: 'Unknown',
                            jurisdiction: manualJurisdiction,
                            company_number: manualLei.trim(),
                            incorporation_date: '',
                            status: 'ACTIVE',
                            _manual: true,
                          });
                          setSelectedRegion(_countryToRegion(manualJurisdiction));
                          setStep(1);
                        }}
                        disabled={!manualName.trim()}
                        className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
                    >
                        Continue <ArrowRight className="w-4 h-4" />
                    </button>
                )}

                {step === 1 && (
                    <button 
                        onClick={() => setStep(2)}
                        className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
                    >
                        Confirm Identity <ArrowRight className="w-4 h-4" />
                    </button>
                )}
                
                {step === 2 && (
                    <button 
                        onClick={handleTrigger}
                        className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors shadow-lg shadow-emerald-900/20"
                    >
                        <CheckCircle2 className="w-4 h-4" /> Start Ingestion
                    </button>
                )}
            </div>
        )}
      </div>
    </div>
  );
};

export default AddCompanyModal;