import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Upload, Download, Sparkles, Image as ImageIcon, Check, Edit3, X, MoveRight, Key, Plus, RefreshCw, Trash2, Play, Paintbrush, Layers, Maximize2, Aperture, Wind, Sliders, User, Palette } from 'lucide-react';
import {
  AppState, GenerationHistoryItem, Character, PhysicalSettings as PhysicalSettingsType,
  MangaStyleSettings as MangaStyleSettingsType, ArtStyleSettings as ArtStyleSettingsType, CharacterColor, CHARACTER_COLOR_ORDER, 
  CHARACTER_COLOR_HEX, CHARACTER_COLOR_LABEL_KO, InputPanelData
} from './types';
import { Button } from './components/Button';
import { PhysicalSettings } from './components/PhysicalSettings';
import { ArtStyleSettings } from './components/ArtStyleSettings';
import { CharacterTabs } from './components/CharacterTabs';
import { Toggle } from './components/Toggle';
import { exportProject, exportCharacter, importZip } from './lib/exportImport';
import { MangaSettings } from './components/MangaSettings';
import { StoryboardEditor } from './components/StoryboardEditor';
import { generateClayModel, generateMangaArt, CharacterInput } from './services/gemini';
import JSZip from 'jszip';
import { saveAs } from 'file-saver';

const pickFreeColor = (used: CharacterColor[]): CharacterColor => {
  for (const c of CHARACTER_COLOR_ORDER) {
    if (!used.includes(c)) return c;
  }
  return CHARACTER_COLOR_ORDER[used.length % CHARACTER_COLOR_ORDER.length];
};

function App() {
  const [hasApiKey, setHasApiKey] = useState<boolean>(false);
  const [isCheckingKey, setIsCheckingKey] = useState<boolean>(true);

  // Layout Tab Mode
  const [activeTab, setActiveTab] = useState<'3d' | 'manga'>('3d');

  // Multi-input Panels
  const [inputs3D, setInputs3D] = useState<InputPanelData[]>([]);
  const [inputsManga, setInputsManga] = useState<InputPanelData[]>([]);

  // History & Characters
  const [history, setHistory] = useState<GenerationHistoryItem[]>([]);
  const [characters, setCharacters] = useState<Character[]>([{
    id: '1',
    name: 'Character 1',
    color: 'red',
    facePrompt: '',
    faceImages: [],
    outfitSets: [{ id: '1_o', name: 'Default Outfit', prompt: '', images: [] }],
    activeOutfitSetId: '1_o'
  }]);
  const [activeCharacterId, setActiveCharacterId] = useState<string>('1');
  const [sceneCharacterIds, setSceneCharacterIds] = useState<string[]>(['1']);

  // Settings
  const [physicalSettings, setPhysicalSettings] = useState<PhysicalSettingsType>({
    windStrength: 0,
    windDirection: 'Front',
    gravityEnabled: true
  });
  const [artStyleSettings, setArtStyleSettings] = useState<ArtStyleSettingsType>({
    images: [],
    prompt: ''
  });
  const [mangaStyleSettings, setMangaStyleSettings] = useState<MangaStyleSettingsType>({
    images: [],
    features: ''
  });

  // Section enable toggles
  const [useArtStyle, setUseArtStyle] = useState<boolean>(true);
  const [useCharacters, setUseCharacters] = useState<boolean>(true);

  // UI state
  const [lightboxImage, setLightboxImage] = useState<string | null>(null);
  const [editingStoryboardId, setEditingStoryboardId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  
  // Refs
  const physicalSettingsRef = useRef(physicalSettings);
  const mangaStyleSettingsRef = useRef(mangaStyleSettings);
  const artStyleSettingsRef = useRef(artStyleSettings);
  const useArtStyleRef = useRef(useArtStyle);
  const useCharactersRef = useRef(useCharacters);
  useEffect(() => { physicalSettingsRef.current = physicalSettings; }, [physicalSettings]);
  useEffect(() => { mangaStyleSettingsRef.current = mangaStyleSettings; }, [mangaStyleSettings]);
  useEffect(() => { artStyleSettingsRef.current = artStyleSettings; }, [artStyleSettings]);
  useEffect(() => { useArtStyleRef.current = useArtStyle; }, [useArtStyle]);
  useEffect(() => { useCharactersRef.current = useCharacters; }, [useCharacters]);

  // Load history & state
  useEffect(() => {
    const savedKey = localStorage.getItem('gemini_api_key');
    if (savedKey) setHasApiKey(true);
    setIsCheckingKey(false);

    const savedHistory = localStorage.getItem('claymorph_history');
    if (savedHistory) {
      try { setHistory(JSON.parse(savedHistory)); } catch (e) {}
    }

    const savedState = localStorage.getItem('claymorph_state_v3');
    if (savedState) {
      try {
        const parsed = JSON.parse(savedState);
        if (parsed.characters?.length > 0) {
          setCharacters(parsed.characters);
          setActiveCharacterId(parsed.activeCharacterId || parsed.characters[0].id);
          setSceneCharacterIds(parsed.sceneCharacterIds || [parsed.characters[0].id]);
        }
        if (parsed.inputs3D) setInputs3D(parsed.inputs3D);
        if (parsed.inputsManga) setInputsManga(parsed.inputsManga);
        if (parsed.physicalSettings) setPhysicalSettings(parsed.physicalSettings);
        if (parsed.mangaStyleSettings) setMangaStyleSettings(parsed.mangaStyleSettings);
        if (parsed.artStyleSettings) setArtStyleSettings(parsed.artStyleSettings);
        if (typeof parsed.useArtStyle === 'boolean') setUseArtStyle(parsed.useArtStyle);
        if (typeof parsed.useCharacters === 'boolean') setUseCharacters(parsed.useCharacters);
      } catch (e) {}
    }
  }, []);

  // Save state
  useEffect(() => {
    if (characters.length > 0) {
      const charsWithoutImages = characters.map(c => ({...c, faceImages: [], outfitSets: c.outfitSets.map(o => ({...o, images: []}))}));
      try {
        localStorage.setItem('claymorph_state_v3', JSON.stringify({
          characters: charsWithoutImages,
          activeCharacterId,
          sceneCharacterIds,
          inputs3D,
          inputsManga,
          physicalSettings,
          mangaStyleSettings,
          artStyleSettings,
          useArtStyle,
          useCharacters
        }));
      } catch (e) {
        console.warn("Failed to save state to localStorage", e);
      }
    }
  }, [characters, activeCharacterId, sceneCharacterIds, inputs3D, inputsManga, physicalSettings, mangaStyleSettings, artStyleSettings, useArtStyle, useCharacters]);

  // Save history
  useEffect(() => {
    try {
      localStorage.setItem('claymorph_history', JSON.stringify(history));
    } catch (e) {
      console.warn("Failed to save history", e);
    }
  }, [history]);

  // Global Paste Handler for Images
  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      const activeEl = document.activeElement;
      if (activeEl && (activeEl.tagName === 'TEXTAREA' || activeEl.tagName === 'INPUT')) {
          return;
      }

      const items = e.clipboardData?.items;
      if (items) {
        for (let i = 0; i < items.length; i++) {
          if (items[i].type.indexOf('image') !== -1) {
            const file = items[i].getAsFile();
            if (file) {
              processInputFile(file);
              e.preventDefault();
            }
          }
        }
      }
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, [activeTab]);

  // Character Handlers
  const handleAddCharacter = () => {
    const usedColors = characters.map(c => c.color);
    const newColor = pickFreeColor(usedColors);
    const newId = Date.now().toString();
    const newChar: Character = {
      id: newId,
      name: `Ch ${characters.length + 1}`,
      color: newColor,
      facePrompt: '',
      faceImages: [],
      outfitSets: [{ id: newId + '_o', name: 'Default Outfit', prompt: '', images: [] }],
      activeOutfitSetId: newId + '_o'
    };
    setCharacters([...characters, newChar]);
    setActiveCharacterId(newChar.id);
  };

  const handleUpdateCharacter = (id: string, updates: Partial<Character>) => {
    setCharacters(prev => prev.map(c => c.id === id ? { ...c, ...updates } : c));
  };

  const handleDeleteCharacter = (id: string) => {
    if (characters.length <= 1) return;
    const remaining = characters.filter(c => c.id !== id);
    if (remaining.length > 0) {
      setCharacters(remaining);
      if (activeCharacterId === id) setActiveCharacterId(remaining[0].id);
      setSceneCharacterIds(prev => {
        const filtered = prev.filter(x => x !== id);
        return filtered.length > 0 ? filtered : [remaining[0].id];
      });
    }
  };

  const handleCloneCharacter = (id: string) => {
    const char = characters.find(c => c.id === id);
    if (char) {
      const usedColors = characters.map(c => c.color);
      const newColor = pickFreeColor(usedColors);
      const clone: Character = {
        ...char,
        id: Date.now().toString(),
        name: `${char.name} (Clone)`,
        color: newColor,
      };
      setCharacters([...characters, clone]);
      setActiveCharacterId(clone.id);
    }
  };

  const handleSetCharacterColor = (id: string, color: CharacterColor) => {
    setCharacters(prev => prev.map(c => c.id === id ? { ...c, color } : c));
  };

  const handleToggleSceneInclusion = (id: string) => {
    setSceneCharacterIds(prev => {
      if (prev.includes(id)) {
        if (prev.length === 1) return prev;
        return prev.filter(x => x !== id);
      }
      return [...prev, id];
    });
  };

  const [isAnalyzingArtStyle, setIsAnalyzingArtStyle] = useState(false);
  const handleAnalyzeArtStyle = async () => {
    if (artStyleSettings.images.length === 0) return;
    setIsAnalyzingArtStyle(true);
    try {
      const { analyzeReferenceImages } = await import('./services/gemini');
      const result = await analyzeReferenceImages(artStyleSettings.images, 'appearance-style');
      setArtStyleSettings(prev => ({ ...prev, prompt: result }));
    } catch (e: any) {
      alert("Analysis failed: " + (e.message || "Unknown error"));
    } finally {
      setIsAnalyzingArtStyle(false);
    }
  };

  // Export / Import
  const handleExportProject = async () => {
    try {
      await exportProject(characters, history);
    } catch (e) {
      console.error(e);
      alert("Failed to export project: " + (e as Error).message);
    }
  };

  const handleExportCharacter = async (id: string) => {
    const char = characters.find(c => c.id === id);
    if (!char) return;
    try {
      await exportCharacter(char, history);
    } catch (e) {
      console.error(e);
      alert("Failed to export character: " + (e as Error).message);
    }
  };

  const handleImportZip = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      try {
        const imported = await importZip(file);
        if (imported) {
          if (imported.characters.length > 0) {
             const usedColors = characters.map(c => c.color);
             const newChars = imported.characters.map((c: any) => {
                const newId = Date.now().toString() + Math.random().toString().slice(2, 6);
                const color = c.color || pickFreeColor(usedColors);
                usedColors.push(color);
                return { ...c, id: newId, color };
             });
             setCharacters(prev => [...prev, ...newChars]);
             setActiveCharacterId(newChars[0].id);
          }
          if (imported.history.length > 0) {
             setHistory(prev => [...imported.history, ...prev]);
          }
        }
      } catch (err) {
        console.error(err);
        alert("Failed to import zip: " + (err as Error).message);
      }
    }
    if (e.target) e.target.value = '';
  };

  // Inputs Handlers
  const processInputFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      if (ev.target?.result) {
        const newItem: InputPanelData = {
           id: Date.now().toString() + Math.random(),
           image: ev.target.result as string,
           prompt: '',
           status: AppState.IDLE,
           hasGenerated: false
        };
        if (activeTab === '3d') setInputs3D(prev => [...prev, newItem]);
        else setInputsManga(prev => [...prev, newItem]);
      }
    };
    reader.readAsDataURL(file);
  };

  const activeInputs = activeTab === '3d' ? inputs3D : inputsManga;
  const setActiveInputs = activeTab === '3d' ? setInputs3D : setInputsManga;

  const updateInputItem = (id: string, updates: Partial<InputPanelData>) => {
     setActiveInputs(prev => prev.map(p => p.id === id ? { ...p, ...updates } : p));
  };

  const deleteInputItem = (id: string) => {
     setActiveInputs(prev => prev.filter(p => p.id !== id));
  };

  const deleteHistory = (id: string) => {
     setHistory(prev => prev.filter(h => h.id !== id));
  };

  const addToMangaInputs = (imageBase64: string) => {
     setInputsManga(prev => [...prev, {
        id: Date.now().toString() + Math.random(),
        image: imageBase64,
        prompt: '',
        status: AppState.IDLE,
        hasGenerated: false
     }]);
     setActiveTab('manga');
  };

  const buildSceneCharacterInputs = (): CharacterInput[] => {
    return characters
      .filter(c => sceneCharacterIds.includes(c.id))
      .map(c => {
        const activeOutfit = c.outfitSets.find(s => s.id === c.activeOutfitSetId);
        return {
          name: c.name,
          color: c.color,
          height: c.height,
          weight: c.weight,
          bodyType: c.bodyType,
          facePrompt: c.facePrompt,
          outfitPrompt: activeOutfit?.prompt || '',
          faceImages: c.faceImages,
          outfitImages: activeOutfit?.images || [],
        };
      });
  };
// Generate logic
  const handleGenerateSingle = async (inputItem: InputPanelData) => {
      if (!inputItem || !inputItem.image) return;

      updateInputItem(inputItem.id, { status: AppState.LOADING, error: undefined });

      try {
         const sceneChars = buildSceneCharacterInputs();
         let resultBase64 = '';
         
         if (activeTab === '3d') {
             resultBase64 = await generateClayModel({
                 imageBase64: inputItem.image,
                 userPrompt: inputItem.prompt,
                 styleImages: useArtStyleRef.current ? artStyleSettingsRef.current.images : [],
                 styleFeatures: useArtStyleRef.current ? artStyleSettingsRef.current.prompt : '',
                 physical: physicalSettingsRef.current,
                 characters: useCharactersRef.current ? sceneChars : []
             });
         } else {
             resultBase64 = await generateMangaArt({
                 imageBase64: inputItem.image,
                 userPrompt: inputItem.prompt,
                 styleImages: mangaStyleSettingsRef.current.images,
                 styleFeatures: mangaStyleSettingsRef.current.features,
                 characters: useCharactersRef.current ? sceneChars : []
             });
         }

         updateInputItem(inputItem.id, { status: AppState.SUCCESS, hasGenerated: true });

         setHistory(prev => [{
            id: Date.now().toString() + Math.random(),
            originalImage: inputItem.image,
            generatedImage: resultBase64,
            prompt: inputItem.prompt,
            timestamp: Date.now(),
            type: activeTab,
            charactersInfo: sceneChars.map(c => ({
              name: c.name,
              color: c.color as CharacterColor, 
              height: c.height,
              weight: c.weight,
              bodyType: c.bodyType,
              facePrompt: c.facePrompt,
              outfitPrompt: c.outfitPrompt
            })),
            physicalInfo: physicalSettingsRef.current
         }, ...prev]);

      } catch (err: any) {
         updateInputItem(inputItem.id, { status: AppState.ERROR, error: err.message });
      }
  };

  const handleGenerateAllActive = async () => {
      for (const item of activeInputs) {
          if (item.image) {
             await handleGenerateSingle(item);
          }
      }
  };

  const handleDownloadAllRecent = async () => {
      const items = history.filter(h => h.type === activeTab);
      if (items.length === 0) return;
      
      const zip = new JSZip();
      items.forEach((item, idx) => {
         const ext = item.generatedImage.includes('image/jpeg') ? 'jpeg' : 'png';
         const data = item.generatedImage.replace(/^data:image\/[a-z]+;base64,/, "");
         zip.file(`output_${activeTab}_${idx + 1}.${ext}`, data, { base64: true });
      });

      const content = await zip.generateAsync({ type: 'blob' });
      saveAs(content, `sequencegen_${activeTab}_export_${Date.now()}.zip`);
  };

  // File drop
  const handleDrop = (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files).filter((f: any) => f.type.startsWith('image/'));
      files.forEach((f: any) => processInputFile(f as File));
  };


  const sceneCharactersForGuide = characters.filter(c => sceneCharacterIds.includes(c.id));
  const SceneColorGuide = () => (
    <div className="mt-2 mb-3 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs shadow-inner shrink-0">
      <div className="text-slate-600 font-bold mb-2">Scene Character Guide:</div>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {sceneCharactersForGuide.length > 0 ? sceneCharactersForGuide.map(c => (
          <div key={c.id} className="flex items-center gap-1.5">
            <span 
              className="inline-block w-3.5 h-3.5 rounded-full border-2" 
              style={{ borderColor: CHARACTER_COLOR_HEX[c.color], backgroundColor: 'transparent' }}
            />
            <span className="text-slate-700 font-medium">{c.name} ({CHARACTER_COLOR_LABEL_KO[c.color]})</span>
          </div>
        )) : (
          <span className="text-slate-400">No characters active in scene. Enable in Character Checkboxes.</span>
        )}
      </div>
    </div>
  );

  const editingInputPanel = activeInputs.find(p => p.id === editingStoryboardId);

  return (
    <div className="flex h-screen bg-slate-100 font-sans text-slate-800 overflow-hidden">
        
       {/* Left Column (Settings & Characters) */}
       <div className="w-[20%] min-w-[240px] max-w-[320px] bg-white border-r border-slate-200 flex flex-col z-20 shadow-[4px_0_24px_rgba(0,0,0,0.02)] h-full overflow-hidden">
          
          <div className="p-3 border-b border-slate-200 shrink-0 flex items-center justify-between">
              <h1 className="font-bold text-sm flex items-center gap-1.5">
                 <div className="bg-slate-800 text-white p-1 rounded min-w-[20px] flex items-center justify-center shadow-sm"><Layers size={14} /></div>
                 SeqGen
              </h1>
              {!hasApiKey ? (
                 <div className="text-[10px] uppercase font-bold text-amber-500 flex items-center bg-amber-50 px-2 py-1 rounded shadow-sm border border-amber-200">
                    <Key size={12} className="mr-1" /> No Key
                 </div>
              ) : (
                 <div className="text-[10px] uppercase font-bold text-green-600 flex items-center bg-green-50 px-2 py-1 rounded shadow-sm border border-green-200">
                    <Check size={12} className="mr-1" /> Active
                 </div>
              )}
          </div>
          
          <div className="flex border-b border-slate-200 bg-slate-50 shrink-0">
              <button 
                className={`flex-1 flex justify-center items-center gap-2 py-3.5 text-sm font-semibold border-b-[3px] transition-colors ${activeTab === '3d' ? 'border-indigo-600 text-indigo-700 bg-white' : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-100/50'}`} 
                onClick={() => setActiveTab('3d')}
              >
                 <Aperture size={16} /> 1. Generate 3D
              </button>
              <button 
                className={`flex-1 flex justify-center items-center gap-2 py-3.5 text-sm font-semibold border-b-[3px] transition-colors ${activeTab === 'manga' ? 'border-rose-600 text-rose-700 bg-white' : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-100/50'}`} 
                onClick={() => setActiveTab('manga')}
              >
                 <Paintbrush size={16} /> 2. Make Manga
              </button>
          </div>

          <div className="flex-1 overflow-y-auto p-5 scrollbar-hide flex flex-col gap-6 pb-20">
              {activeTab === '3d' ? (
                 <div className="animate-in fade-in slide-in-from-left-4 duration-300">
                    <ArtStyleSettings 
                      settings={artStyleSettings} 
                      onChange={setArtStyleSettings} 
                      onAnalyze={handleAnalyzeArtStyle}
                      isAnalyzing={isAnalyzingArtStyle}
                      enabled={useArtStyle}
                      onToggleEnabled={setUseArtStyle}
                    />
                 </div>
              ) : (
                 <div className="animate-in fade-in slide-in-from-left-4 duration-300">
                    <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2"><Sliders size={14} /> Manga Style</h2>
                    <MangaSettings settings={mangaStyleSettings} onChange={setMangaStyleSettings} />
                 </div>
              )}
              
              <div className="h-px w-full bg-slate-200 shrink-0 my-2" />

              <div>
                 <div className="flex justify-between items-center mb-3">
                     <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2"><User size={14} /> Cast & Crew</h2>
                     <div className="flex items-center gap-1.5">
                       <Toggle enabled={useCharacters} onChange={setUseCharacters} label="Use characters" />
                       {useCharacters && (
                         <Button size="sm" variant="secondary" onClick={handleAddCharacter} className="text-slate-700 font-bold px-2 h-7 text-[10px]" title="Add Character">
                           <Plus size={12} className="mr-0.5" /> Character
                         </Button>
                       )}
                     </div>
                 </div>
                 {useCharacters && (
                   <CharacterTabs 
                      characters={characters}
                      activeCharacterId={activeCharacterId}
                      sceneCharacterIds={sceneCharacterIds}
                      onSetActiveCharacter={setActiveCharacterId}
                      onAddCharacter={handleAddCharacter}
                      onUpdateCharacter={handleUpdateCharacter}
                      onDeleteCharacter={handleDeleteCharacter}
                      onCloneCharacter={handleCloneCharacter}
                      onExportCharacter={handleExportCharacter}
                      onSetCharacterColor={handleSetCharacterColor}
                      onToggleSceneInclusion={handleToggleSceneInclusion}
                   />
                 )}
              </div>

              <div className="h-px w-full bg-slate-200 shrink-0 my-2" />
              
              <div className="animate-in fade-in slide-in-from-bottom-4 duration-300">
                 <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2"><Wind size={14} /> Physical Dynamics</h2>
                 <PhysicalSettings settings={physicalSettings} onChange={setPhysicalSettings} />
              </div>
          </div>

          <div className="p-4 border-t border-slate-200 bg-slate-50 shrink-0 flex flex-col gap-2 relative z-20">
             <div className="flex gap-2">
                 <Button variant="outline" onClick={() => document.getElementById('import-project')?.click()} className="flex-1 text-xs h-9 text-slate-600 bg-white hover:bg-slate-50">
                    <Upload size={14} className="mr-2" /> Import
                 </Button>
                 <input type="file" id="import-project" className="hidden" accept=".zip" onChange={handleImportZip} />
                 <Button variant="outline" onClick={handleExportProject} className="flex-1 text-xs h-9 text-slate-600 bg-white hover:bg-slate-50">
                    <Download size={14} className="mr-2" /> Export
                 </Button>
             </div>
          </div>
       </div>

       {/* Right Column (Inputs & Outputs) */}
       <div className="flex-1 flex flex-row h-full relative overflow-hidden bg-slate-100/50">
           
           {/* Left Half: Input Board */}
           <div 
             className={`w-1/2 border-r border-slate-300 flex flex-col overflow-hidden transition-colors ${isDragging ? 'bg-indigo-50/50' : 'bg-transparent'}`}
             onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
             onDragLeave={() => setIsDragging(false)}
             onDrop={handleDrop}
           >
               <div className="p-4 bg-white/80 backdrop-blur-md border-b border-slate-200 flex justify-between items-center z-10 shrink-0">
                  <div>
                     <h2 className="font-bold text-slate-800 flex items-center gap-2">
                         {activeTab === '3d' ? 'Storyboard Board' : 'Manga Base Inputs'}
                     </h2>
                  </div>
                  <div className="flex items-center gap-3">
                      <Button onClick={handleGenerateAllActive} className={`shadow-md shadow-${activeTab === '3d' ? 'indigo' : 'rose'}-200/50 font-bold ${activeTab === '3d' ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-rose-600 hover:bg-rose-700'} text-white`}>
                          {activeTab === '3d' ? <><Aperture size={16} className="mr-2" /> Make All 3D</> : <><Paintbrush size={16} className="mr-2" /> Make All Manga</>}
                      </Button>
                  </div>
               </div>

               <div className="flex-1 overflow-y-auto p-3 sm:p-4 lg:p-6 flex flex-col">
                  
                  {activeTab === '3d' && useCharacters && <SceneColorGuide />}

                  <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-4 gap-4 lg:gap-6 pb-20">
                      {activeInputs.map((item, idx) => (
                           <div key={item.id} className="flex flex-col group/panel">
                               {/* Thumbnail Box */}
                               <div className={`relative aspect-square w-full bg-slate-100 rounded-xl overflow-hidden shadow-sm border ${item.status === AppState.ERROR ? 'border-red-300 ring-2 ring-red-100' : 'border-slate-200'} transition-all hover:shadow-md group/img`}>
                                   <div className="absolute top-2 left-2 z-20 pointer-events-none">
                                       <div className="bg-black/60 backdrop-blur-sm text-white text-[10px] font-bold px-2 py-0.5 rounded shadow-sm">#{idx + 1}</div>
                                   </div>
                                   <button onClick={() => deleteInputItem(item.id)} className="absolute top-2 right-2 bg-black/40 backdrop-blur-sm p-1.5 rounded-full opacity-0 group-hover/img:opacity-100 hover:bg-red-500 text-white z-10 shadow-sm transition-all">
                                      <Trash2 size={12} />
                                   </button>
                                   
                                   <img src={item.image} className="w-full h-full object-cover" />
                                   
                                   {activeTab === '3d' && (
                                      <button onClick={() => setEditingStoryboardId(item.id)} className="absolute bottom-2 right-2 bg-black/60 p-2 rounded-full shadow hover:scale-110 text-white opacity-0 group-hover/img:opacity-100 transition-all border border-white/20" title="Draw mapping lines">
                                         <Edit3 size={14} />
                                      </button>
                                   )}
                                   {item.status === AppState.LOADING && (
                                      <div className="absolute inset-0 bg-white/80 flex items-center justify-center backdrop-blur-sm">
                                         <div className="w-8 h-8 border-4 border-slate-200 border-t-indigo-600 rounded-full animate-spin"></div>
                                      </div>
                                   )}
                               </div>
                               
                               {/* Input Controls Container */}
                               <div className="mt-2 flex flex-col gap-2">
                                  <textarea 
                                     value={item.prompt} 
                                     onChange={(e) => updateInputItem(item.id, { prompt: e.target.value })}
                                     className="text-[10px] sm:text-[11px] font-medium text-slate-700 p-2 rounded-lg bg-white border border-slate-200 focus:bg-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-300 outline-none resize-none h-16 w-full shadow-sm transition-all placeholder:text-slate-400"
                                     placeholder="Prompt..."
                                  />
                                  
                                  <Button 
                                      size="sm" 
                                      isLoading={item.status === AppState.LOADING} 
                                      onClick={() => handleGenerateSingle(item)} 
                                      className={`w-full flex justify-center py-1.5 h-auto items-center font-bold text-[11px] rounded shadow-sm ${item.hasGenerated ? 'bg-slate-200 text-slate-700 hover:bg-slate-300' : 'bg-slate-800 text-white hover:bg-slate-700'}`}
                                  >
                                      {item.hasGenerated ? <RefreshCw size={12} className="mr-1.5 opacity-70" /> : (activeTab === '3d' ? <Aperture size={12} className="mr-1.5 opacity-70" /> : <Paintbrush size={12} className="mr-1.5 opacity-70" />)}
                                      {item.hasGenerated ? 'Retry' : 'Gen'}
                                  </Button>
                                  {item.error && <p className="text-[9px] text-red-500 font-semibold truncate" title={item.error}>{item.error}</p>}
                               </div>
                           </div>
                      ))}

                      <div className="flex flex-col">
                          <label className="border-2 border-dashed border-slate-300 rounded-xl flex flex-col items-center justify-center p-2 text-slate-400 hover:text-slate-600 hover:border-slate-400 hover:bg-white cursor-pointer transition-all group aspect-square w-full">
                              <input type="file" multiple accept="image/*" className="hidden" onChange={e => Array.from(e.target.files||[]).forEach(processInputFile)} />
                              <div className="w-8 h-8 bg-slate-100 rounded-full flex items-center justify-center mb-1 group-hover:bg-slate-50 group-hover:scale-110 transition-all">
                                  <Plus size={16} className="text-slate-400" />
                              </div>
                              <span className="text-[10px] font-bold tracking-tight">Add Images</span>
                          </label>
                      </div>
                  </div>
               </div>
           </div>

           {/* Right Half: Recent Results */}
           <div className="w-1/2 flex flex-col overflow-hidden bg-slate-50 shrink-0 z-20 shadow-[-4px_0_24px_rgba(0,0,0,0.02)]">
               <div className="px-3 py-2 bg-white border-b border-slate-200 flex justify-between items-center sticky top-0 z-10 shrink-0">
                  <h2 className="font-bold text-slate-800 text-xs flex items-center gap-1.5">
                     <ImageIcon size={14} className="text-slate-400" /> 
                     Recent {activeTab === '3d' ? '3D' : 'Manga'}
                  </h2>
                  <Button size="sm" variant="outline" onClick={handleDownloadAllRecent} className="shadow-sm bg-white hover:bg-slate-50 h-7 px-2 font-semibold text-[10px]">
                     <Download size={12} className="mr-1" /> Get Zip
                  </Button>
               </div>

<div className="flex-1 overflow-y-auto p-3 sm:p-4 lg:px-6">
                   <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 pb-12">
                       {history.filter(h => h.type === activeTab).map(h => (
                           <div key={h.id} className="bg-white p-2 rounded-xl border border-slate-200 shadow-sm relative group aspect-[3/4] hover:shadow-md hover:-translate-y-1 transition-all overflow-hidden cursor-zoom-in" onClick={() => setLightboxImage(h.generatedImage)}>
                               <img src={h.generatedImage} className="w-full h-full object-cover rounded-lg group-hover:opacity-95 transition-opacity bg-slate-100" loading="lazy" />
                               
                               <div className="absolute top-3 right-3 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-all z-10 translate-y-1 group-hover:translate-y-0">
                                   <button 
                                     onClick={(e) => { e.stopPropagation(); deleteHistory(h.id); }}
                                     className="bg-white/95 backdrop-blur-sm p-1.5 rounded-full shadow text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                                     title="Delete"
                                   >
                                       <Trash2 size={14} />
                                   </button>
                                   {h.type === '3d' && (
                                       <button 
                                         onClick={(e) => { e.stopPropagation(); addToMangaInputs(h.generatedImage); }}
                                         className="bg-indigo-600/95 backdrop-blur-sm p-1.5 rounded-full shadow text-white hover:bg-indigo-500 transition-colors"
                                         title="Send to Manga Phase"
                                       >
                                           <MoveRight size={14} />
                                       </button>
                                   )}
                               </div>

                               <div className="absolute inset-x-2 bottom-2 p-3 bg-gradient-to-t from-black/90 via-black/50 to-transparent rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end pointer-events-none">
                                   <p className="text-white text-xs font-semibold line-clamp-2 leading-relaxed">{h.prompt || 'No descriptive prompt'}</p>
                                   <p className="text-white/60 text-[9px] mt-1.5 font-bold uppercase tracking-wider">{new Date(h.timestamp).toLocaleTimeString()}</p>
                               </div>
                           </div>
                       ))}
                   </div>
                   
                   {history.filter(h => h.type === activeTab).length === 0 && (
                       <div className="w-full h-full flex flex-col items-center justify-center text-slate-400 font-medium">
                           <ImageIcon size={32} className="mb-3 opacity-30" />
                           <p>No recent {activeTab === '3d' ? '3D' : 'manga'} outputs yet.</p>
                       </div>
                   )}
               </div>
           </div>
       </div>

       {/* Storyboard Editor Modal */}
       {editingInputPanel && editingInputPanel.image && (
          <StoryboardEditor 
             open={!!editingStoryboardId}
             initialImage={editingInputPanel.image}
             sceneCharacters={characters.filter(c => sceneCharacterIds.includes(c.id))}
             onClose={() => setEditingStoryboardId(null)}
             onSave={(img) => { updateInputItem(editingInputPanel.id, { image: img }); }}
          />
       )}

       {/* Lightbox Modal */}
       {lightboxImage && (
          <div 
            className="fixed inset-0 z-[100] bg-slate-900/95 backdrop-blur-md flex flex-col items-center justify-center cursor-zoom-out animate-in fade-in zoom-in-95 duration-200"
            onClick={() => setLightboxImage(null)}
          >
             <div className="absolute top-6 right-6 z-[110]">
                <Button 
                  variant="ghost" size="sm" 
                  onClick={() => setLightboxImage(null)}
                  className="text-white/70 hover:text-white bg-white/10 hover:bg-white/20 rounded-full w-12 h-12 p-0 flex items-center justify-center transition-all backdrop-blur"
                >
                  <X size={24} />
                </Button>
             </div>
             
             <img 
                src={lightboxImage}
                onClick={(e) => e.stopPropagation()} 
                className="max-w-[95vw] max-h-[95vh] object-contain shadow-2xl rounded-sm pointer-events-auto"
                alt="Full preview"
             />
          </div>
       )}

    </div>
  );
}

export default App;
