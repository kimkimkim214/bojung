export type StudyMode = 'vocab' | 'kanji' | 'radical';

export interface KanjiItem {
  id: string;
  word: string; // The Japanese word or single Kanji
  kanaReading: string; // Japanese reading in Hiragana/Katakana
  hangulReading: string; // Japanese pronunciation (for vocab) OR Korean reading (for kanji) in Hangul
  meaning: string; // Korean meaning
  example: string; // Simple Japanese example
  level: string; // JLPT level
}

export type AppPhase = 'landing' | 'study';
