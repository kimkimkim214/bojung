import React from 'react';
import { ArtStyleSettings as ArtStyleSettingsType } from '../types';
import { ReferenceManager } from './ReferenceManager';
import { Palette } from 'lucide-react';
import { Toggle } from './Toggle';

interface ArtStyleSettingsProps {
  settings: ArtStyleSettingsType;
  onChange: (settings: ArtStyleSettingsType) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  enabled?: boolean;
  onToggleEnabled?: (v: boolean) => void;
}

export function ArtStyleSettings({
  settings,
  onChange,
  onAnalyze,
  isAnalyzing,
  enabled = true,
  onToggleEnabled,
}: ArtStyleSettingsProps) {
  const handleAddImages = (newImages: string[]) => {
    onChange({ ...settings, images: [...settings.images, ...newImages] });
  };

  const handleRemoveImage = (index: number) => {
    onChange({ ...settings, images: settings.images.filter((_, i) => i !== index) });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-slate-800 text-sm flex items-center gap-1.5">
          <Palette size={14} className="text-slate-600" />
          Appearance Style Reference
        </h3>
        {onToggleEnabled && (
          <Toggle enabled={enabled} onChange={onToggleEnabled} label="Use art style" />
        )}
      </div>
      {enabled && (
        <div className="p-4 rounded-xl border border-slate-200 bg-white shadow-sm space-y-4">
          <ReferenceManager
            title="Style Images"
            images={settings.images}
            onAddImages={handleAddImages}
            onRemoveImage={handleRemoveImage}
            onAnalyze={onAnalyze}
            isAnalyzing={isAnalyzing}
            promptValue={settings.prompt}
            onPromptChange={(val) => onChange({ ...settings, prompt: val })}
          />
        </div>
      )}
    </div>
  );
}
