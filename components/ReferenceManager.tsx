import React, { useRef, useState } from 'react';
import { Image as ImageIcon, X, Sparkles, Plus, Trash2 } from 'lucide-react';
import { Button } from './Button';

interface ReferenceManagerProps {
  title: string;
  description?: string;
  images: string[];
  onAddImages: (newImages: string[]) => void;
  onRemoveImage: (index: number) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  promptValue: string;
  onPromptChange: (val: string) => void;
}

export const ReferenceManager: React.FC<ReferenceManagerProps> = ({
  title,
  description,
  images,
  onAddImages,
  onRemoveImage,
  onAnalyze,
  isAnalyzing,
  promptValue,
  onPromptChange,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const processFiles = (files: FileList | null) => {
    if (!files) return;
    const newImages: string[] = [];
    Array.from(files).forEach((file) => {
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onloadend = () => {
          onAddImages([reader.result as string]);
        };
        reader.readAsDataURL(file);
      }
    });
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (items) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          const file = items[i].getAsFile();
          if (file) {
            const reader = new FileReader();
            reader.onloadend = () => {
              onAddImages([reader.result as string]);
            };
            reader.readAsDataURL(file);
          }
        }
      }
    }
  };

  return (
    <div 
      className="space-y-4"
      onPaste={handlePaste}
    >
      <div className="flex justify-between items-center whitespace-nowrap">
        <h4 className="font-bold text-slate-800 text-sm truncate mr-2">{title}</h4>
        <Button
          variant="secondary"
          size="sm"
          onClick={onAnalyze}
          isLoading={isAnalyzing}
          disabled={images.length === 0}
          className="text-[10px] font-bold py-1 h-6 px-2 shrink-0"
        >
          <Sparkles size={12} className="mr-1" />
          Analyze
        </Button>
      </div>

      <div
        className={`grid grid-cols-4 gap-2 p-3 rounded-xl border-2 border-dashed transition-all ${
          isDragging ? 'border-slate-500 bg-slate-50' : 'border-slate-200 hover:border-slate-300'
        }`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => { e.preventDefault(); setIsDragging(false); processFiles(e.dataTransfer.files); }}
        onClick={() => fileInputRef.current?.click()}
      >
        {images.map((img, idx) => (
          <div key={idx} className="relative aspect-square group">
            <img src={img} className="w-full h-full object-cover rounded-lg" />
            <button
              onClick={(e) => { e.stopPropagation(); onRemoveImage(idx); }}
              className="absolute -top-1 -right-1 p-1 bg-red-500 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
        {images.length < 8 && (
          <div className="aspect-square flex flex-col items-center justify-center text-slate-400 bg-slate-50 rounded-lg cursor-pointer">
            <Plus size={20} />
            <span className="text-[10px] mt-1">Add</span>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*"
          className="hidden"
          onChange={(e) => processFiles(e.target.files)}
        />
      </div>

      <textarea
        value={promptValue}
        onChange={(e) => onPromptChange(e.target.value)}
        placeholder={`Extracted ${title} prompt (editable)...`}
        className="w-full h-24 p-3 text-sm border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:ring-2 focus:ring-slate-100 outline-none resize-none transition-all"
      />
    </div>
  );
};
