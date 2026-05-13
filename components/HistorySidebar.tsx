import React from 'react';
import { GenerationHistoryItem } from '../types';
import { Trash2, Clock } from 'lucide-react';

interface HistorySidebarProps {
  history: GenerationHistoryItem[];
  onSelect: (item: GenerationHistoryItem) => void;
  onDelete: (id: string, e: React.MouseEvent) => void;
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
}

export const HistorySidebar: React.FC<HistorySidebarProps> = ({ 
  history, 
  onSelect, 
  onDelete, 
  isOpen, 
  setIsOpen 
}) => {
  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/20 z-20 lg:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      <div className={`fixed top-0 right-0 h-full w-80 bg-white shadow-2xl z-30 transform transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : 'translate-x-full'} flex flex-col border-l border-slate-100`}>
        <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
          <h2 className="font-semibold text-slate-800 flex items-center gap-2">
            <Clock size={18} />
            History
          </h2>
          <button 
            onClick={() => setIsOpen(false)}
            className="text-slate-400 hover:text-slate-600 p-1"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {history.length === 0 ? (
            <div className="text-center text-slate-400 mt-10">
              <p>No sketches saved yet.</p>
            </div>
          ) : (
            history.map((item) => (
              <div 
                key={item.id}
                onClick={() => onSelect(item)}
                className="group relative bg-white border border-slate-200 rounded-xl overflow-hidden cursor-pointer hover:border-slate-400 hover:shadow-md transition-all"
              >
                <div className="aspect-[4/3] bg-slate-100 relative">
                  <img 
                    src={item.generatedImage} 
                    alt="Generated 3D Model" 
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute bottom-0 right-0 p-1 bg-black/50 text-white text-xs rounded-tl-md">
                    3D
                  </div>
                </div>
                <div className="p-3">
                  <p className="text-sm text-slate-600 line-clamp-2 italic">
                     "{item.prompt || 'No prompt'}"
                  </p>
                  <p className="text-xs text-slate-400 mt-2">
                    {new Date(item.timestamp).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={(e) => onDelete(item.id, e)}
                  className="absolute top-2 right-2 p-1.5 bg-white/90 text-red-500 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-50"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
};