import React from 'react';

interface ToggleProps {
  enabled: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}

export const Toggle: React.FC<ToggleProps> = ({ enabled, onChange, label }) => (
  <button
    type="button"
    role="switch"
    aria-checked={enabled}
    aria-label={label || 'Toggle'}
    title={label}
    onClick={() => onChange(!enabled)}
    className={`relative w-8 h-[18px] rounded-full transition-colors shrink-0 ${enabled ? 'bg-slate-800' : 'bg-slate-300'}`}
  >
    <span
      className={`absolute top-0.5 w-[14px] h-[14px] rounded-full bg-white shadow transition-transform ${enabled ? 'translate-x-[15px]' : 'translate-x-0.5'}`}
    />
  </button>
);
