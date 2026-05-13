import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Pencil, Eraser, Undo, Redo, ZoomIn, ZoomOut, Save, X, RotateCcw, Edit3 } from 'lucide-react';
import { CHARACTER_COLOR_HEX, Character } from '../types';
import { Button } from './Button';

interface StoryboardEditorProps {
  open: boolean;
  initialImage: string | null;
  sceneCharacters: Character[];
  onClose: () => void;
  onSave: (imageData: string) => void;
}

export const StoryboardEditor: React.FC<StoryboardEditorProps> = ({ 
  open, initialImage, sceneCharacters, onClose, onSave 
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [color, setColor] = useState<string>('#000000');
  const [tool, setTool] = useState<'pen' | 'eraser'>('pen');
  const [brushSize, setBrushSize] = useState(6);
  const [history, setHistory] = useState<ImageData[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [zoom, setZoom] = useState(1);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [scale, setScale] = useState(1);
  const [cursorPos, setCursorPos] = useState<{x: number, y: number} | null>(null);
  const [isHovering, setIsHovering] = useState(false);

  const MAX_HISTORY = 10;
  const MAX_DIM = 800;

  // Initialize
  useEffect(() => {
    if (!open || !initialImage) return;
    
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) return;

    const img = new Image();
    img.src = initialImage;
    img.crossOrigin = "anonymous";
    img.onload = () => {
      let w = img.naturalWidth;
      let h = img.naturalHeight;
      if (w > MAX_DIM || h > MAX_DIM) {
        const r = Math.min(MAX_DIM / w, MAX_DIM / h);
        w *= r; h *= r;
      }
      canvas.width = w;
      canvas.height = h;
      ctx.drawImage(img, 0, 0, w, h);
      
      const initialData = ctx.getImageData(0, 0, w, h);
      setHistory([initialData]);
      setHistoryIndex(0);
      setImageLoaded(true);

      // Fit to view
      if (containerRef.current) {
         const { clientWidth, clientHeight } = containerRef.current;
         const pad = 60;
         const sx = (clientWidth - pad) / w;
         const sy = (clientHeight - pad) / h;
         setZoom(Math.min(1, sx, sy));
      }
    };
  }, [open, initialImage]);

  const updateScale = useCallback(() => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    setScale(rect.width / canvasRef.current.width);
  }, [zoom]);

  useEffect(() => {
    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, [updateScale]);

  const saveToHistory = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const newData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push(newData);
    if (newHistory.length > MAX_HISTORY) newHistory.shift();
    setHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);
  };

  const undo = () => {
    if (historyIndex > 0) {
      const idx = historyIndex - 1;
      setHistoryIndex(idx);
      restore(history[idx]);
    }
  };

  const restore = (data: ImageData) => {
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) ctx.putImageData(data, 0, 0);
  };

  const getPos = (e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (canvas.width / rect.width),
      y: (e.clientY - rect.top) * (canvas.height / rect.height)
    };
  };

  const startDraw = (e: React.PointerEvent) => {
    if (!imageLoaded) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setIsDrawing(true);
    const pos = getPos(e);
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) {
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
    }
  };

  const doDraw = (e: React.PointerEvent) => {
    if (canvasRef.current) {
        const rect = canvasRef.current.getBoundingClientRect();
        setCursorPos({ x: e.clientX, y: e.clientY });
        setIsHovering(e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom);
    }
    if (!isDrawing) return;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    const pos = getPos(e);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = brushSize;
    ctx.strokeStyle = tool === 'eraser' ? '#FFFFFF' : color;
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
  };

  const stopDraw = (e: React.PointerEvent) => {
    if (isDrawing) {
      setIsDrawing(false);
      saveToHistory();
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4 lg:p-8 animate-in fade-in duration-200">
      <div className="bg-white w-full max-w-6xl h-full flex flex-col rounded-3xl shadow-2xl overflow-hidden border border-slate-200">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-100 bg-slate-50">
           <div className="flex items-center gap-3">
              <div className="p-2 bg-slate-800 text-white rounded-lg">
                <Edit3 size={20} fill="currentColor" />
              </div>
              <div>
                <h2 className="font-bold text-slate-800">Identify Characters</h2>
                <p className="text-[10px] text-slate-500 font-medium">Draw color borders around character regions</p>
              </div>
           </div>
           <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={onClose} className="rounded-full w-10 h-10 p-0 text-slate-400">
                 <X size={24} />
              </Button>
           </div>
        </div>

        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
           
           {/* Sidebar Tools */}
           <div className="lg:w-64 bg-slate-50 border-r border-slate-100 p-4 space-y-6 overflow-y-auto">
              {/* Tools */}
              <div className="space-y-2">
                 <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Tools</label>
                 <div className="grid grid-cols-2 gap-2">
                    <button 
                      onClick={() => setTool('pen')}
                      className={`flex items-center justify-center gap-2 py-2 rounded-lg border transition-all ${tool === 'pen' ? 'bg-slate-800 text-white border-slate-800 shadow-md' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'}`}
                    >
                       <Pencil size={16} />
                       <span className="text-xs font-semibold">Pen</span>
                    </button>
                    <button 
                      onClick={() => setTool('eraser')}
                      className={`flex items-center justify-center gap-2 py-2 rounded-lg border transition-all ${tool === 'eraser' ? 'bg-slate-800 text-white border-slate-800 shadow-md' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'}`}
                    >
                       <Eraser size={16} />
                       <span className="text-xs font-semibold">Eraser</span>
                    </button>
                 </div>
              </div>

              {/* Character Palette */}
              <div className="space-y-3">
                 <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Character Colors</label>
                 <div className="space-y-2">
                    <button 
                       onClick={() => { setColor('#000000'); setTool('pen'); }}
                       className={`w-full flex items-center gap-3 p-2 rounded-xl transition-all border-2 ${color === '#000000' && tool === 'pen' ? 'border-slate-800 bg-white ring-2 ring-slate-100' : 'border-transparent hover:bg-slate-100'}`}
                    >
                       <div className="w-6 h-6 rounded-lg bg-black shrink-0 border border-black/10" />
                       <span className="text-xs font-medium text-slate-700">Basic Sketch</span>
                    </button>
                    
                    {sceneCharacters.map(char => (
                       <button 
                          key={char.id}
                          onClick={() => { setColor(CHARACTER_COLOR_HEX[char.color]); setTool('pen'); }}
                          className={`w-full flex items-center gap-3 p-2 rounded-xl transition-all border-2 ${color === CHARACTER_COLOR_HEX[char.color] && tool === 'pen' ? 'border-slate-800 bg-white ring-2 ring-slate-100' : 'border-transparent hover:bg-slate-100 group'}`}
                       >
                          <div 
                             className="w-6 h-6 rounded-lg shrink-0 border-2" 
                             style={{ borderColor: CHARACTER_COLOR_HEX[char.color] }} 
                          />
                          <div className="flex flex-col items-start overflow-hidden">
                             <span className="text-[11px] font-bold text-slate-800 truncate w-full">{char.name}</span>
                             <span className="text-[9px] text-slate-400">Mapping Color</span>
                          </div>
                          {color === CHARACTER_COLOR_HEX[char.color] && tool === 'pen' && <div className="ml-auto w-2 h-2 rounded-full bg-slate-800" />}
                       </button>
                    ))}
                    
                    {sceneCharacters.length === 0 && (
                       <p className="text-[10px] text-slate-400 bg-slate-100/50 p-3 rounded-lg border border-dashed border-slate-200">
                          Include characters in the scene via the Character tab to use color mapping.
                       </p>
                    )}
                 </div>
              </div>

              <div className="space-y-2">
                 <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Brush Size</label>
                 <input 
                    type="range" min="1" max="40" value={brushSize} 
                    onChange={(e) => setBrushSize(parseInt(e.target.value))}
                    className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-slate-800"
                 />
                 <div className="flex justify-between text-[9px] font-bold text-slate-400 px-1">
                    <span>SM</span>
                    <span>MD</span>
                    <span>LG</span>
                 </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex gap-2">
                 <button 
                   onClick={undo} 
                   disabled={historyIndex <= 0}
                   className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-30 transition-all"
                 >
                    <Undo size={14} />
                    <span className="text-xs font-semibold">Undo</span>
                 </button>
                 <button 
                    onClick={() => {
                        const ctx = canvasRef.current?.getContext('2d');
                        if (ctx && initialImage) {
                            const img = new Image();
                            img.src = initialImage;
                            img.onload = () => {
                                ctx.clearRect(0,0, canvasRef.current!.width, canvasRef.current!.height);
                                ctx.drawImage(img, 0, 0, canvasRef.current!.width, canvasRef.current!.height);
                                saveToHistory();
                            }
                        }
                    }}
                    className="p-2 rounded-lg text-slate-400 hover:text-slate-800 hover:bg-slate-200 transition-all"
                    title="Reset Changes"
                 >
                    <RotateCcw size={16} />
                 </button>
              </div>
           </div>

           {/* Canvas Viewport */}
           <div className="flex-1 bg-slate-100 relative overflow-hidden flex flex-col">
              {/* Zoom indicators */}
              <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-3 bg-white/80 backdrop-blur-md px-4 py-2 rounded-full border border-slate-200 shadow-sm transition-opacity group-hover:opacity-100">
                  <button onClick={() => setZoom(z => Math.max(0.1, z - 0.1))} className="p-1 hover:bg-slate-200 rounded transition-colors"><ZoomOut size={16} /></button>
                  <span className="text-xs font-mono font-bold text-slate-600">{Math.round(zoom * 100)}%</span>
                  <button onClick={() => setZoom(z => Math.min(4, z + 0.1))} className="p-1 hover:bg-slate-200 rounded transition-colors"><ZoomIn size={16} /></button>
              </div>

              <div 
                ref={containerRef}
                className="flex-1 overflow-auto touch-none flex items-center justify-center p-8 active:cursor-grabbing"
              >
                 <div 
                   className="bg-white shadow-2xl relative transition-all duration-75"
                   style={{ 
                     width: canvasRef.current ? canvasRef.current.width * zoom : 'auto',
                     height: canvasRef.current ? canvasRef.current.height * zoom : 'auto',
                   }}
                 >
                    <canvas 
                      ref={canvasRef}
                      onPointerDown={startDraw}
                      onPointerMove={doDraw}
                      onPointerUp={stopDraw}
                      onPointerLeave={stopDraw}
                      className="block w-full h-full cursor-crosshair touch-none"
                    />
                 </div>

                 {isHovering && cursorPos && (
                    <div 
                       className="pointer-events-none fixed rounded-full border-2 z-[110]"
                       style={{
                          left: cursorPos.x, top: cursorPos.y,
                          width: brushSize * scale * zoom, height: brushSize * scale * zoom,
                          transform: 'translate(-50%, -50%)',
                          borderColor: tool === 'eraser' ? '#ccc' : color,
                          boxShadow: '0 0 0 1px white'
                       }}
                    />
                 )}
              </div>
              
              {/* Manual/Guide help */}
              <div className="absolute bottom-4 left-4 right-4 text-center pointer-events-none">
                 <span className="inline-block px-4 py-2 bg-slate-800/80 text-white text-[10px] font-medium rounded-full backdrop-blur-sm shadow-lg">
                    Guide: Use specific colors to circle parts of the image for mapping characters.
                 </span>
              </div>
           </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 bg-white flex justify-between items-center px-8">
           <div className="text-[10px] text-slate-400 font-medium max-w-xs">
              Draw closed loops (circles/blobs) around characters using their assigned mapping colors. 
              The AI will use these regions as identity identifiers.
           </div>
           <div className="flex gap-3">
              <Button variant="ghost" onClick={onClose} className="px-6 text-slate-500">Cancel</Button>
              <Button 
                onClick={() => {
                  const canvas = canvasRef.current;
                  if (canvas) onSave(canvas.toDataURL());
                  onClose();
                }}
                className="px-10 py-3 shadow-lg shadow-slate-200"
              >
                 <Save size={18} className="mr-2" />
                 Apply Changes
              </Button>
           </div>
        </div>
      </div>
    </div>
  );
};
