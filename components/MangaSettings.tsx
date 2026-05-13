import React, { useRef, useState } from 'react';
import { Upload, X, Search } from 'lucide-react';
import { MangaStyleSettings } from '../types';
import { analyzeReferenceImages } from '../services/gemini';
import { Button } from './Button';

interface MangaSettingsProps {
  settings: MangaStyleSettings;
  onChange: (settings: MangaStyleSettings) => void;
}

export const MangaSettings: React.FC<MangaSettingsProps> = ({ settings, onChange }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const processFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const imageFiles = Array.from(files).filter((file) => file.type.startsWith('image/'));
    if (imageFiles.length === 0) return;

    const newImages: string[] = [];
    let loadedCount = 0;

    imageFiles.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        if (ev.target?.result && typeof ev.target.result === 'string') {
          newImages.push(ev.target.result);
        }
        loadedCount++;
        if (loadedCount === imageFiles.length) {
          onChange({
            ...settings,
            images: [...settings.images, ...newImages],
          });
        }
      };
      reader.readAsDataURL(file);
    });
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    processFiles(e.target.files);
    if (e.target) e.target.value = '';
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const dt = new DataTransfer();
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        const file = items[i].getAsFile();
        if (file) dt.items.add(file);
      }
    }
    if (dt.files.length > 0) {
      processFiles(dt.files);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    processFiles(e.dataTransfer.files);
  };

  const handleRemoveImage = (index: number) => {
    const newImages = [...settings.images];
    newImages.splice(index, 1);
    onChange({ ...settings, images: newImages });
  };

  const handleAnalyze = async () => {
    if (settings.images.length === 0) return;
    setIsAnalyzing(true);
    try {
      // Create a slight variant of analysis or use 'face' as dummy to just use the structure,
      // but let's just make analyzeReferenceImages generic later or use a different function.
      // Wait, let's use the provided one for now or add a new context 'manga-style' in gemini.ts

      const features = await analyzeReferenceImages(settings.images, 'manga-style' as any);
      onChange({ ...settings, features });
    } catch (e) {
      console.error(e);
      alert("Analysis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div
      className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200"
      onPaste={handlePaste}
    >
      <h2 className="text-lg font-semibold mb-4 text-slate-800">Manga Style Reference (Project Global)</h2>

      <p className="text-xs text-slate-500 mb-4">
        Upload pen-line manga samples to define line thickness, halftones, and shading style. You can also paste (Cmd/Ctrl+V) or drag & drop images.
      </p>

      {/* Uploaded Images */}
      {settings.images.length > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-4 mb-4">
          {settings.images.map((img, idx) => (
            <div key={idx} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 shrink-0 group">
              <img src={img} alt="Style Ref" className="w-full h-full object-cover" />
              <button
                onClick={() => handleRemoveImage(idx)}
                className="absolute top-1 right-1 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </div>
          ))}

          <button
             onClick={() => fileInputRef.current?.click()}
             onDragOver={handleDragOver}
             onDragLeave={handleDragLeave}
             onDrop={handleDrop}
             className={`w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center shrink-0 transition-colors ${
               isDragging
                 ? 'border-slate-500 bg-slate-100 text-slate-600'
                 : 'border-slate-300 text-slate-400 hover:text-slate-600 hover:border-slate-400'
             }`}
          >
            <Upload size={16} className="mb-1" />
            <span className="text-[10px] font-medium">Add More</span>
          </button>
        </div>
      )}

      {settings.images.length === 0 && (
         <div
           onClick={() => fileInputRef.current?.click()}
           onDragOver={handleDragOver}
           onDragLeave={handleDragLeave}
           onDrop={handleDrop}
           className={`w-full h-24 mb-6 rounded-xl border-2 border-dashed flex flex-col items-center justify-center cursor-pointer transition-colors ${
             isDragging
               ? 'border-slate-500 bg-slate-100 text-slate-600'
               : 'border-slate-200 hover:border-slate-300 text-slate-400 bg-slate-50 hover:bg-slate-100'
           }`}
         >
           <Upload size={20} className="mb-2" />
           <p className="text-xs font-medium">Upload Manga Style Images</p>
           <p className="text-[10px] text-slate-400 mt-1">Click, paste (Cmd/Ctrl+V), or drag & drop</p>
         </div>
      )}

      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        multiple
        accept="image/*"
        onChange={handleFileUpload}
      />

      <div className="space-y-3">
         <div className="flex items-center justify-between">
           <label className="text-sm font-medium text-slate-700">Extracted Style Features</label>
           <Button variant="secondary" size="sm" onClick={handleAnalyze} disabled={settings.images.length === 0 || isAnalyzing}>
              {isAnalyzing ? "Analyzing..." : <><Search size={14} className="mr-1" /> Analyze</>}
           </Button>
         </div>
         <textarea
            value={settings.features}
            onChange={(e) => onChange({ ...settings, features: e.target.value })}
            placeholder="E.g., Thick brush pen strokes, dense cross-hatching, sparse screentones..."
            className="w-full h-24 p-3 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white text-xs resize-none outline-none focus:ring-1 focus:ring-slate-300 transition-all font-mono"
         />
      </div>
    </div>
  );
};
