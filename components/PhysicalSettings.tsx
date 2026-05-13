import React from 'react';
import { Wind, MoveDown } from 'lucide-react';
import { WindStrength, WindDirection, PhysicalSettings as PhysicalSettingsType } from '../types';

interface PhysicalSettingsProps {
  settings: PhysicalSettingsType;
  onChange: (settings: PhysicalSettingsType) => void;
}

const DIRECTIONS: WindDirection[] = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'Front', 'Back'];

export const PhysicalSettings: React.FC<PhysicalSettingsProps> = ({ settings, onChange }) => {
  return (
    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-6">
      <div className="flex items-center gap-2 mb-2">
        <Wind size={18} className="text-slate-600" />
        <h3 className="font-semibold text-slate-800">Physical Descriptors</h3>
      </div>

      {/* Wind Strength */}
      <div className="space-y-2">
        <div className="flex justify-between items-center text-sm">
          <span className="text-slate-600 font-medium">Wind Strength</span>
          <span className="text-slate-400">
            {['None', 'Light', 'Moderate', 'Strong', 'Storm'][settings.windStrength]}
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="4"
          step="1"
          value={settings.windStrength}
          onChange={(e) => onChange({ ...settings, windStrength: parseInt(e.target.value) as WindStrength })}
          className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-slate-800"
        />
        <div className="flex justify-between text-[10px] text-slate-400 px-1">
          <span>None</span>
          <span>Storm</span>
        </div>
      </div>

      {/* Wind Direction Dial */}
      <div className="space-y-3">
        <span className="text-sm text-slate-600 font-medium">Wind Direction</span>
        <div className="grid grid-cols-5 gap-2">
          {DIRECTIONS.map((dir) => (
            <button
              key={dir}
              onClick={() => onChange({ ...settings, windDirection: dir })}
              className={`py-1 px-2 text-[10px] rounded-md border transition-all ${
                settings.windDirection === dir
                  ? 'bg-slate-800 border-slate-800 text-white font-bold shadow-sm scale-110'
                  : 'bg-slate-50 border-slate-200 text-slate-500 hover:bg-slate-100'
              }`}
            >
              {dir}
            </button>
          ))}
        </div>
      </div>

      {/* Gravity */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-100">
        <div className="flex items-center gap-2">
          <MoveDown size={16} className="text-slate-400" />
          <span className="text-sm text-slate-600 font-medium">Auto Gravity</span>
        </div>
        <button
          onClick={() => onChange({ ...settings, gravityEnabled: !settings.gravityEnabled })}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            settings.gravityEnabled ? 'bg-slate-800' : 'bg-slate-200'
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              settings.gravityEnabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>
    </div>
  );
};
