export enum AppState {
  IDLE = 'IDLE',
  LOADING = 'LOADING',
  SUCCESS = 'SUCCESS',
  ERROR = 'ERROR'
}

export type WindStrength = 0 | 1 | 2 | 3 | 4 | 5;
export type WindDirection = 'N' | 'NE' | 'E' | 'SE' | 'S' | 'SW' | 'W' | 'NW' | 'Front' | 'Back';

export type CharacterColor = 'red' | 'blue' | 'green' | 'amber';

export const CHARACTER_COLOR_ORDER: CharacterColor[] = ['red', 'blue', 'green', 'amber'];

export interface InputPanelData {
  id: string;
  image: string;
  prompt: string;
  status: AppState;
  error?: string;
  hasGenerated?: boolean;
}

export const CHARACTER_COLOR_HEX: Record<CharacterColor, string> = {
  red: '#ef4444',
  blue: '#3b82f6',
  green: '#22c55e',
  amber: '#f59e0b'
};

export const CHARACTER_COLOR_LABEL_KO: Record<CharacterColor, string> = {
  red: '빨간색',
  blue: '파란색',
  green: '초록색',
  amber: '노란색'
};

export interface OutfitSet {
  id: string;
  name: string;
  prompt: string;
  images: string[]; // Base64
}

export interface Character {
  id: string;
  name: string;
  color: CharacterColor;
  height?: string;
  weight?: string;
  bodyType?: string;
  facePrompt: string;
  faceImages: string[]; // Base64
  outfitSets: OutfitSet[];
  activeOutfitSetId: string;
}

export interface PhysicalSettings {
  windStrength: WindStrength;
  windDirection: WindDirection;
  gravityEnabled: boolean;
}

export interface ArtStyleSettings {
  images: string[];
  prompt: string;
}

export interface MangaStyleSettings {
  images: string[]; // Base64
  features: string; // extracted text
}

export interface GenerationHistoryItem {
  id: string;
  originalImage: string; // Base64
  generatedImage: string; // Base64
  prompt: string;
  timestamp: number;
  type?: '3d' | 'manga'; // track step type
  charactersInfo?: {
    name: string;
    color: CharacterColor;
    height?: string;
    weight?: string;
    bodyType?: string;
    facePrompt: string;
    outfitPrompt: string;
  }[];
  physicalInfo?: PhysicalSettings;
}
