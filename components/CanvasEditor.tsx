import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Pencil, Eraser, Undo, Redo, ZoomIn, ZoomOut, Maximize, Minimize } from 'lucide-react';

interface CanvasEditorProps {
  initialImage: string;
  onUpdate: (imageData: string) => void;
}

export const CanvasEditor: React.FC<CanvasEditorProps> = ({ initialImage, onUpdate }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // State
  const [isDrawing, setIsDrawing] = useState(false);
  const [tool, setTool] = useState<'pen' | 'eraser'>('pen');
  const [brushSize, setBrushSize] = useState(10);
  const [history, setHistory] = useState<ImageData[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [imageLoaded, setImageLoaded] = useState(false);
  
  // Zoom & Layout State
  const [zoom, setZoom] = useState(1);
  const [scale, setScale] = useState(1); // Internal calc for cursor sizing
  const [cursorPos, setCursorPos] = useState<{x: number, y: number} | null>(null);
  const [isHovering, setIsHovering] = useState(false);

  // Constants
  const MAX_HISTORY = 5; // Reduced to 5 to safe memory
  const MAX_IMAGE_DIMENSION = 700; // Reduced to 700px for maximum stability

  // Initialize Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) return;

    const img = new Image();
    img.src = initialImage;
    img.onload = () => {
      let width = img.naturalWidth;
      let height = img.naturalHeight;

      // Aggressive Downscale Logic to prevent crashes
      if (width > MAX_IMAGE_DIMENSION || height > MAX_IMAGE_DIMENSION) {
         const ratio = Math.min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height);
         width = Math.round(width * ratio);
         height = Math.round(height * ratio);
      }

      // Set canvas size
      canvas.width = width;
      canvas.height = height;
      
      // Draw image (scaling if needed)
      ctx.drawImage(img, 0, 0, width, height);
      
      // Initial History
      const initialData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      setHistory([initialData]);
      setHistoryIndex(0);
      setImageLoaded(true);
      onUpdate(canvas.toDataURL());

      // Calculate initial Zoom to Fit
      if (containerRef.current) {
         const { clientWidth, clientHeight } = containerRef.current;
         const padding = 40;
         const scaleX = (clientWidth - padding) / width;
         const scaleY = (clientHeight - padding) / height;
         const fitScale = Math.min(scaleX, scaleY);
         setZoom(Math.min(1, fitScale)); 
      }
    };
  }, [initialImage]);

  // Update layout scale for cursor
  const updateLayoutScale = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (canvas.width > 0) {
      setScale(rect.width / canvas.width);
    }
  }, [zoom]);

  useEffect(() => {
    updateLayoutScale();
    window.addEventListener('resize', updateLayoutScale);
    return () => window.removeEventListener('resize', updateLayoutScale);
  }, [updateLayoutScale]);

  // Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.repeat) return;
      
      const key = e.key.toLowerCase();

      // Tools
      if (key === 'b') setTool('pen');
      if (key === 'e') setTool('eraser');

      // Brush Size
      if (key === '[') setBrushSize(prev => Math.max(1, prev - 5));
      if (key === ']') setBrushSize(prev => Math.min(100, prev + 5));
      
      // Undo/Redo
      if ((e.ctrlKey || e.metaKey) && key === 'z') {
        e.preventDefault();
        if (e.shiftKey) handleRedo();
        else handleUndo();
      }
      if ((e.ctrlKey || e.metaKey) && key === 'y') {
        e.preventDefault();
        handleRedo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [historyIndex, history]);

  const saveToHistory = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const newData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push(newData);
    
    // Limit history stack size
    if (newHistory.length > MAX_HISTORY) newHistory.shift();

    setHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);
    onUpdate(canvas.toDataURL());
  };

  const handleUndo = () => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      setHistoryIndex(newIndex);
      restoreState(history[newIndex]);
    }
  };

  const handleRedo = () => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setHistoryIndex(newIndex);
      restoreState(history[newIndex]);
    }
  };

  const restoreState = (imageData: ImageData) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.putImageData(imageData, 0, 0);
    onUpdate(canvas.toDataURL());
  };

  // -------------------------
  // Drawing Logic
  // -------------------------
  
  const getPointerPos = (e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    
    const rect = canvas.getBoundingClientRect();
    // Map client coordinates to canvas internal coordinates
    const x = (e.clientX - rect.left) * (canvas.width / rect.width);
    const y = (e.clientY - rect.top) * (canvas.height / rect.height);
    
    return { x, y };
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    // Cursor Tracking
    if (canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      if (
          e.clientX >= rect.left && 
          e.clientX <= rect.right && 
          e.clientY >= rect.top && 
          e.clientY <= rect.bottom
      ) {
          setIsHovering(true);
          setCursorPos({ x: e.clientX, y: e.clientY });
      } else {
          setIsHovering(false);
          setCursorPos(null);
      }
    }

    if (isDrawing) {
        draw(e);
    }
  };

  const startDrawing = (e: React.PointerEvent) => {
    if (!imageLoaded) return;
    // Only Draw with Left Click (button 0) or Pen
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    
    setIsDrawing(true);
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!ctx) return;
    
    ctx.beginPath();
    const { x, y } = getPointerPos(e);
    ctx.moveTo(x, y);
    draw(e);
  };

  const draw = (e: React.PointerEvent) => {
    if (!isDrawing) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!ctx) return;

    const { x, y } = getPointerPos(e);
    
    const pressure = e.pressure === 0 ? 0.5 : e.pressure;
    const currentLineWidth = brushSize * (e.pointerType === 'pen' ? pressure : 1);

    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = currentLineWidth;
    
    if (tool === 'eraser') {
      ctx.globalCompositeOperation = 'source-over';
      ctx.strokeStyle = '#FFFFFF';
    } else {
      ctx.globalCompositeOperation = 'source-over';
      ctx.strokeStyle = '#000000'; // Black brush
    }

    ctx.lineTo(x, y);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const stopDrawing = (e: React.PointerEvent) => {
    if (isDrawing) {
      setIsDrawing(false);
      saveToHistory();
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    }
  };

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between bg-slate-100 p-2 rounded-lg border border-slate-200 shrink-0 select-none">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTool('pen')}
            className={`p-2 rounded-md transition-colors ${tool === 'pen' ? 'bg-slate-800 text-white' : 'hover:bg-slate-200 text-slate-700'}`}
            title="Pen Tool (B)"
          >
            <Pencil size={18} />
          </button>
          <button
            onClick={() => setTool('eraser')}
            className={`p-2 rounded-md transition-colors ${tool === 'eraser' ? 'bg-slate-800 text-white' : 'hover:bg-slate-200 text-slate-700'}`}
            title="Eraser Tool (E)"
          >
            <Eraser size={18} />
          </button>
          
          <div className="h-6 w-px bg-slate-300 mx-1"></div>
          
          <div className="flex items-center gap-2 px-2">
            <span className="text-xs font-bold text-slate-500 whitespace-nowrap hidden sm:inline">Brush: {brushSize}px</span>
            <input 
              type="range" 
              min="1" 
              max="100" 
              value={brushSize} 
              onChange={(e) => setBrushSize(Number(e.target.value))}
              className="w-20 sm:w-24 h-2 bg-slate-300 rounded-lg appearance-none cursor-pointer accent-slate-800"
            />
          </div>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1 bg-white rounded-md border border-slate-200 p-1">
            <button onClick={() => setZoom(z => Math.max(0.1, z - 0.1))} className="p-1 hover:bg-slate-100 rounded text-slate-600">
                <ZoomOut size={16} />
            </button>
            <span className="text-xs font-mono w-10 text-center">{Math.round(zoom * 100)}%</span>
            <button onClick={() => setZoom(z => Math.min(5, z + 0.1))} className="p-1 hover:bg-slate-100 rounded text-slate-600">
                <ZoomIn size={16} />
            </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleUndo}
            disabled={historyIndex <= 0}
            className="p-2 text-slate-700 hover:bg-slate-200 rounded-md disabled:opacity-30 disabled:cursor-not-allowed"
            title="Undo (Ctrl+Z)"
          >
            <Undo size={18} />
          </button>
          <button
            onClick={handleRedo}
            disabled={historyIndex >= history.length - 1}
            className="p-2 text-slate-700 hover:bg-slate-200 rounded-md disabled:opacity-30 disabled:cursor-not-allowed"
            title="Redo (Ctrl+Y)"
          >
            <Redo size={18} />
          </button>
        </div>
      </div>

      {/* Canvas Scroll Area */}
      <div 
        ref={containerRef}
        className="flex-1 bg-slate-200/50 rounded-xl border-2 border-slate-200 overflow-auto relative touch-none flex items-center justify-center p-4 cursor-grab active:cursor-grabbing"
        style={{ 
          backgroundImage: 'radial-gradient(#cbd5e1 1px, transparent 1px)', 
          backgroundSize: '20px 20px' 
        }}
      >
        {/* Canvas Wrapper */}
        <div 
            className="relative shadow-lg bg-white transition-all duration-75 ease-out"
            style={{ 
                // Explicitly set dimensions based on zoom
                width: canvasRef.current ? canvasRef.current.width * zoom : 'auto',
                height: canvasRef.current ? canvasRef.current.height * zoom : 'auto',
            }}
        >
            <canvas
                ref={canvasRef}
                onPointerDown={startDrawing}
                onPointerMove={handlePointerMove}
                onPointerUp={stopDrawing}
                onPointerLeave={(e) => {
                    stopDrawing(e);
                    setIsHovering(false);
                }}
                className={`block touch-none ${isHovering ? 'cursor-none' : 'cursor-crosshair'}`}
                style={{
                    width: '100%',
                    height: '100%',
                }}
            />
        </div>
        
        {/* Brush Cursor (Fixed Position) */}
        {isHovering && cursorPos && (
            <div 
                className="pointer-events-none fixed rounded-full border border-black z-50 bg-transparent"
                style={{
                    left: cursorPos.x,
                    top: cursorPos.y,
                    width: brushSize * scale * zoom, // Scale brush visual by zoom level
                    height: brushSize * scale * zoom,
                    transform: 'translate(-50%, -50%)',
                    boxShadow: '0 0 0 1px rgba(255, 255, 255, 0.9), inset 0 0 0 1px rgba(255,255,255,0.2)'
                }}
            />
        )}
        
        {!imageLoaded && (
           <div className="absolute inset-0 flex items-center justify-center text-slate-400">
             Loading image...
           </div>
        )}
      </div>
       <div className="text-xs text-slate-400 px-1 flex justify-between">
          <span>Shortcuts: [B]rush, [E]raser, [ ] size, Ctrl+Z undo</span>
          <span>Scroll to pan (when zoomed)</span>
       </div>
    </div>
  );
};