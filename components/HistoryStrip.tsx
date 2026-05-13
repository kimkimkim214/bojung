import React from 'react';
import { GenerationHistoryItem } from '../types';
import { Trash2, ImageIcon } from 'lucide-react';

interface HistoryStripProps {
  history: GenerationHistoryItem[];
  onSelect: (item: GenerationHistoryItem) => void;
  onDelete: (id: string, e: React.MouseEvent) => void;
}

export const HistoryStrip: React.FC<HistoryStripProps> = ({ 
  history, 
  onSelect, 
  onDelete 
}) => {
  if (history.length === 0) return null;

  return (
    <div className="w-full bg-white border-t border-slate-200 p-4 shadow-inner">
      <h3 className="text-sm font-semibold text-slate-500 mb-3 px-2">Recent Creations</h3>
      <div className="flex gap-4 overflow-x-auto pb-2 scrollbar-hide snap-x">
        {history.map((item) => (
          <div 
            key={item.id}
            onClick={() => onSelect(item)}
            className="group relative flex-shrink-0 w-32 aspect-square bg-slate-100 rounded-lg overflow-hidden border border-slate-200 hover:border-slate-400 cursor-pointer snap-start transition-all hover:shadow-md"
          >
            <img 
              src={item.generatedImage} 
              alt="Thumbnail" 
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
            
            {/* Delete button */}
            <button
              onClick={(e) => onDelete(item.id, e)}
              className="absolute top-1 right-1 p-1 bg-white/90 text-red-500 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-50 shadow-sm"
              title="Delete"
            >
              <Trash2 size={12} />
            </button>
            
            <div className="absolute bottom-0 inset-x-0 p-1.5 bg-gradient-to-t from-black/60 to-transparent">
               <p className="text-[10px] text-white truncate px-1">
                 {item.prompt || 'Untitled'}
               </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};