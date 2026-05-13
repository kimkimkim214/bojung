import React, { useState } from 'react';
import { User, Plus, X, MoreHorizontal, Copy, Trash2, Edit2, Shirt, Download, Check } from 'lucide-react';
import { Character, OutfitSet, CharacterColor, CHARACTER_COLOR_HEX, CHARACTER_COLOR_ORDER } from '../types';
import { Button } from './Button';
import { ReferenceManager } from './ReferenceManager';
import { analyzeReferenceImages } from '../services/gemini';

interface CharacterTabsProps {
  characters: Character[];
  activeCharacterId: string;
  sceneCharacterIds: string[];
  onSetActiveCharacter: (id: string) => void;
  onAddCharacter: () => void;
  onUpdateCharacter: (id: string, updates: Partial<Character>) => void;
  onDeleteCharacter: (id: string) => void;
  onCloneCharacter: (id: string) => void;
  onExportCharacter: (id: string) => void;
  onSetCharacterColor: (id: string, color: CharacterColor) => void;
  onToggleSceneInclusion: (id: string) => void;
}

export const CharacterTabs: React.FC<CharacterTabsProps> = ({
  characters,
  activeCharacterId,
  sceneCharacterIds,
  onSetActiveCharacter,
  onAddCharacter,
  onUpdateCharacter,
  onDeleteCharacter,
  onCloneCharacter,
  onExportCharacter,
  onSetCharacterColor,
  onToggleSceneInclusion,
}) => {
  const activeChar = characters.find(c => c.id === activeCharacterId);
  const [showMenuId, setShowMenuId] = useState<string | null>(null);
  const [analyzingField, setAnalyzingField] = useState<string | null>(null);
  const [showColorPickerId, setShowColorPickerId] = useState<string | null>(null);
  const [editingNameId, setEditingNameId] = useState<string | null>(null);
  const [editingNameValue, setEditingNameValue] = useState<string>("");

  const handleAnalyze = async (type: 'face' | 'outfit', images: string[], setId?: string) => {
    if (images.length === 0) return;
    setAnalyzingField(setId || type);
    try {
      const result = await analyzeReferenceImages(images, type === 'face' ? 'face' : 'outfit');
      if (type === 'face') {
        onUpdateCharacter(activeCharacterId, { facePrompt: result });
      } else if (setId) {
        const char = characters.find(c => c.id === activeCharacterId);
        if (char) {
          const updatedSets = char.outfitSets.map(s => s.id === setId ? { ...s, prompt: result } : s);
          onUpdateCharacter(activeCharacterId, { outfitSets: updatedSets });
        }
      }
    } catch (e: any) {
      console.error(e);
      let errMsg = e?.message || "Unknown error";
      if (typeof e === 'object' && !e?.message) errMsg = JSON.stringify(e);
      alert("Analysis failed: " + errMsg);
    } finally {
      setAnalyzingField(null);
    }
  };

  if (!activeChar) return null;

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
      {/* Vertical Character List (replaces former horizontal tab strip) */}
      <div className="bg-slate-50 border-b border-slate-200 p-1.5 flex flex-col gap-0.5 max-h-[280px] overflow-y-auto scrollbar-hide">
        {characters.map((char) => {
          const isActive = activeCharacterId === char.id;
          const isMenuOpen = showMenuId === char.id;
          const isColorOpen = showColorPickerId === char.id;
          const inScene = sceneCharacterIds.includes(char.id);

          return (
            <div key={char.id} className="w-full">
              {/* Row */}
              <div className="flex items-center gap-1 group">
                {/* Scene Inclusion Checkbox */}
                <button
                  onClick={() => onToggleSceneInclusion(char.id)}
                  className={`w-4 h-4 rounded border flex items-center justify-center transition-colors shrink-0 ${
                    inScene
                      ? 'bg-slate-800 border-slate-800 text-white'
                      : 'bg-white border-slate-300 text-transparent hover:border-slate-400'
                  }`}
                  title="Include in scene"
                >
                  <Check size={10} strokeWidth={4} />
                </button>

                {/* Select character (fills remaining width) */}
                <button
                  onClick={() => onSetActiveCharacter(char.id)}
                  onContextMenu={(e) => { e.preventDefault(); setShowMenuId(isMenuOpen ? null : char.id); setShowColorPickerId(null); }}
                  className={`flex-1 min-w-0 flex items-center gap-2 px-2 py-1.5 text-xs font-medium rounded-md transition-all text-left ${
                    isActive
                      ? 'bg-white text-slate-800 shadow-sm'
                      : 'text-slate-500 hover:bg-slate-100'
                  }`}
                >
                  <span
                    role="button"
                    aria-label="Change mapping color"
                    className="w-2.5 h-2.5 rounded-full shrink-0 border-[1.5px] cursor-pointer"
                    style={{ borderColor: CHARACTER_COLOR_HEX[char.color], backgroundColor: 'transparent' }}
                    onClick={(e) => { e.stopPropagation(); setShowColorPickerId(isColorOpen ? null : char.id); setShowMenuId(null); }}
                    title="Change Mapping Color"
                  />
                  {editingNameId === char.id ? (
                    <input
                      autoFocus
                      value={editingNameValue}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => setEditingNameValue(e.target.value)}
                      onBlur={() => {
                        const v = editingNameValue.trim();
                        if (v) onUpdateCharacter(char.id, { name: v });
                        setEditingNameId(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          const v = editingNameValue.trim();
                          if (v) onUpdateCharacter(char.id, { name: v });
                          setEditingNameId(null);
                        } else if (e.key === 'Escape') {
                          setEditingNameId(null);
                        }
                      }}
                      className="truncate flex-1 min-w-0 bg-white border border-slate-300 rounded px-1 py-0 text-xs outline-none focus:border-indigo-400"
                    />
                  ) : (
                    <span className="truncate flex-1 min-w-0" title={char.name}>{char.name}</span>
                  )}
                </button>

                {/* Hover/Active Actions */}
                <div className={`flex items-center shrink-0 transition-opacity ${isMenuOpen || isColorOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'}`}>
                  <button
                    onClick={(e) => { e.stopPropagation(); setShowMenuId(isMenuOpen ? null : char.id); setShowColorPickerId(null); }}
                    className={`p-1 rounded text-slate-400 hover:text-slate-600 transition-colors ${isMenuOpen ? 'bg-slate-200 text-slate-700' : 'hover:bg-slate-200'}`}
                    title="More"
                  >
                    <MoreHorizontal size={12} />
                  </button>
                  {characters.length > 1 && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onDeleteCharacter(char.id); }}
                      className="p-1 hover:bg-red-100 rounded text-slate-400 hover:text-red-500 transition-colors"
                      title="Delete"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>
              </div>

              {/* Inline expansion: Color Picker */}
              {isColorOpen && (
                <div className="mt-1 mb-1 ml-5 mr-1 p-2 bg-white border border-slate-200 rounded-lg shadow-sm flex gap-1.5 flex-wrap animate-in fade-in slide-in-from-top-1 duration-150">
                  {CHARACTER_COLOR_ORDER.map(color => (
                    <button
                      key={color}
                      onClick={() => { onSetCharacterColor(char.id, color); setShowColorPickerId(null); }}
                      className={`w-5 h-5 rounded-full border-[1.5px] transition-transform hover:scale-110 ${char.color === color ? 'ring-2 ring-slate-800 ring-offset-1' : ''}`}
                      style={{ borderColor: CHARACTER_COLOR_HEX[color] }}
                      title={color}
                    />
                  ))}
                </div>
              )}

              {/* Inline expansion: Menu */}
              {isMenuOpen && (
                <div className="mt-1 mb-1 ml-5 mr-1 bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden animate-in fade-in slide-in-from-top-1 duration-150">
                  <button
                    onClick={() => {
                      setEditingNameId(char.id);
                      setEditingNameValue(char.name);
                      setShowMenuId(null);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50 flex items-center gap-2"
                  >
                    <Edit2 size={11} /> Rename
                  </button>
                  <button
                    onClick={() => { onCloneCharacter(char.id); setShowMenuId(null); }}
                    className="w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50 flex items-center gap-2"
                  >
                    <Copy size={11} /> Clone
                  </button>
                  <button
                    onClick={() => { onExportCharacter(char.id); setShowMenuId(null); }}
                    className="w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50 flex items-center gap-2"
                  >
                    <Download size={11} /> Export Profile
                  </button>
                  {characters.length > 1 && (
                    <button
                      onClick={() => { onDeleteCharacter(char.id); setShowMenuId(null); }}
                      className="w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50 text-red-500 flex items-center gap-2"
                    >
                      <Trash2 size={11} /> Delete
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Character Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-8 scrollbar-hide">
        {/* Physical Attributes */}
        <section className="space-y-3">
          <div className="flex items-center gap-1.5 truncate">
             <User size={14} className="text-slate-600 shrink-0" />
             <h3 className="font-bold text-slate-800 text-sm truncate">Physical Attributes</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input
              type="text"
              placeholder="Height (e.g., 180cm)"
              value={activeChar.height || ''}
              onChange={(e) => onUpdateCharacter(activeChar.id, { height: e.target.value })}
              className="text-xs p-2 rounded-lg bg-slate-50 border border-slate-200 focus:bg-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-300 outline-none w-full shadow-sm"
            />
            <input
              type="text"
              placeholder="Weight (e.g., 75kg)"
              value={activeChar.weight || ''}
              onChange={(e) => onUpdateCharacter(activeChar.id, { weight: e.target.value })}
              className="text-xs p-2 rounded-lg bg-slate-50 border border-slate-200 focus:bg-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-300 outline-none w-full shadow-sm"
            />
            <input
              type="text"
              placeholder="Physique (e.g., Muscular)"
              value={activeChar.bodyType || ''}
              onChange={(e) => onUpdateCharacter(activeChar.id, { bodyType: e.target.value })}
              className="text-xs p-2 rounded-lg bg-slate-50 border border-slate-200 focus:bg-white focus:border-indigo-400 focus:ring-1 focus:ring-indigo-300 outline-none w-full shadow-sm"
            />
          </div>
        </section>

        <div className="h-px bg-slate-100" />

        {/* Face Reference Section */}
        <section>
          <ReferenceManager
            title="Face Ref"
            images={activeChar.faceImages}
            onAddImages={(imgs) => onUpdateCharacter(activeChar.id, { faceImages: [...activeChar.faceImages, ...imgs] })}
            onRemoveImage={(idx) => onUpdateCharacter(activeChar.id, { faceImages: activeChar.faceImages.filter((_, i) => i !== idx) })}
            onAnalyze={() => handleAnalyze('face', activeChar.faceImages)}
            isAnalyzing={analyzingField === 'face'}
            promptValue={activeChar.facePrompt}
            onPromptChange={(val) => onUpdateCharacter(activeChar.id, { facePrompt: val })}
          />
        </section>

        <div className="h-px bg-slate-100" />

        {/* Outfit Reference Section */}
        <section className="space-y-4">
          <div className="flex justify-between items-center mb-2 whitespace-nowrap">
            <div className="flex items-center gap-1.5 truncate mr-2">
              <Shirt size={14} className="text-slate-600 shrink-0" />
              <h3 className="font-bold text-slate-800 text-sm truncate">Outfit Sets</h3>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                const newSet: OutfitSet = { id: Date.now().toString(), name: "New Set", prompt: "", images: [] };
                onUpdateCharacter(activeChar.id, { outfitSets: [...activeChar.outfitSets, newSet] });
              }}
              className="text-[10px] py-1 h-6 px-2 font-bold shrink-0"
            >
              <Plus size={12} className="mr-0.5" /> Add
            </Button>
          </div>

          <div className="space-y-4">
            {activeChar.outfitSets.map((set) => (
              <div key={set.id} className="p-4 rounded-xl border border-slate-100 bg-slate-50/50 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                     <button
                        onClick={() => onUpdateCharacter(activeChar.id, { activeOutfitSetId: set.id })}
                        className={`w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all ${
                          activeChar.activeOutfitSetId === set.id ? 'border-slate-800 bg-slate-800' : 'border-slate-300'
                        }`}
                     >
                        <div className="w-1.5 h-1.5 rounded-full bg-white" />
                     </button>
                     <input 
                        className="font-semibold text-slate-700 bg-transparent border-none focus:ring-0 p-0 text-sm"
                        value={set.name}
                        onChange={(e) => {
                          const updatedSets = activeChar.outfitSets.map(s => s.id === set.id ? { ...s, name: e.target.value } : s);
                          onUpdateCharacter(activeChar.id, { outfitSets: updatedSets });
                        }}
                     />
                  </div>
                  <button 
                    onClick={() => onUpdateCharacter(activeChar.id, { outfitSets: activeChar.outfitSets.filter(s => s.id !== set.id) })}
                    className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <ReferenceManager
                  title="Outfit Details"
                  images={set.images}
                  onAddImages={(imgs) => {
                    const updatedSets = activeChar.outfitSets.map(s => s.id === set.id ? { ...s, images: [...s.images, ...imgs] } : s);
                    onUpdateCharacter(activeChar.id, { outfitSets: updatedSets });
                  }}
                  onRemoveImage={(idx) => {
                     const updatedSets = activeChar.outfitSets.map(s => s.id === set.id ? { ...s, images: s.images.filter((_, i) => i !== idx) } : s);
                     onUpdateCharacter(activeChar.id, { outfitSets: updatedSets });
                  }}
                  onAnalyze={() => handleAnalyze('outfit', set.images, set.id)}
                  isAnalyzing={analyzingField === set.id}
                  promptValue={set.prompt}
                  onPromptChange={(val) => {
                    const updatedSets = activeChar.outfitSets.map(s => s.id === set.id ? { ...s, prompt: val } : s);
                    onUpdateCharacter(activeChar.id, { outfitSets: updatedSets });
                  }}
                />
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};

