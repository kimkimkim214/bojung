import { GoogleGenAI, Type } from "@google/genai";
import { KanjiItem, StudyMode } from "../types";

const DEFAULT_API_KEY = "AIzaSyDdmios51z1GKg8gTOdD7GL2u6Edd2e3dA";
const STORAGE_KEY = "gemini_api_key";

export function getApiKey(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && saved.trim().length > 0) return saved.trim();
  } catch (_) {}
  return DEFAULT_API_KEY;
}

export function setApiKey(key: string) {
  try {
    if (key && key.trim().length > 0) {
      localStorage.setItem(STORAGE_KEY, key.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch (_) {}
}

export function getDefaultApiKey() {
  return DEFAULT_API_KEY;
}

export async function fetchKanjiSet(level: string = "N5", mode: StudyMode = "vocab", count: number = 10, excludeWords: string[] = []): Promise<KanjiItem[]> {
  const ai = new GoogleGenAI({ apiKey: getApiKey() });

  const vocabPrompt = `Generate a list of ${count} unique Japanese vocabulary words (using Kanji where appropriate) for JLPT level ${level}.
  Format the output as a JSON array of objects.
  - word: the Japanese word in Kanji (if applicable)
  - kanaReading: the reading in Hiragana/Katakana
  - hangulReading: the Japanese pronunciation written in Korean Hangul (e.g., '쿄-')
  - meaning: the Korean meaning of the word
  - example: a simple Japanese sentence using this word`;

  const kanjiPrompt = `Generate a list of ${count} unique Japanese Joyo Kanji (common characters) suitable for JLPT level ${level}.
  Format the output as a JSON array of objects.
  - word: the single Kanji character
  - kanaReading: the common Japanese readings (On-yomi/Kun-yomi) in Hiragana/Katakana
  - hangulReading: the Korean reading of the Kanji character (e.g., for '日', it's '일')
  - meaning: the Korean meaning of the Kanji (e.g., for '日', it's '날')
  - example: a simple Japanese word using this Kanji`;

  const radicalPrompt = `Generate a list of ${count} unique Japanese Kanji Radicals (部首, Bushu).
  IMPORTANT: For the 'word' field, provide BOTH the standard form and its common variant used in characters (e.g., '人 (亻)', '水 (氵)', '火 (灬)', '心 (忄)').
  Format the output as a JSON array of objects.
  - word: "Standard (Variant)" format
  - kanaReading: the Japanese name of the radical in Hiragana/Katakana
  - hangulReading: the full Korean name of the radical (e.g., '사람 인', '물 수', '마음 심') - DO NOT include '변', '방', '머리' here.
  - meaning: the core meaning in Korean (e.g., '사람', '물', '마음') - DO NOT include '변', '방', '머리', '인', '수' here.
  - example: a common Kanji that uses this radical`;

  const basePrompt = mode === 'vocab' ? vocabPrompt : mode === 'kanji' ? kanjiPrompt : radicalPrompt;

  const prompt = `${basePrompt}
  - id: a unique string
  - level: ${level}

  CRITICAL EXCLUSION RULE:
  Strictly EXCLUDE these exact strings from the 'word' field in your response: ${excludeWords.join(', ')}.
  Do NOT include any items you have previously provided if they are in the list above.
  Ensuring accurate data for Korean learners of Japanese is paramount.`;

  const config = {
    responseMimeType: "application/json",
    responseSchema: {
      type: Type.ARRAY,
      items: {
        type: Type.OBJECT,
        properties: {
          id: { type: Type.STRING },
          word: { type: Type.STRING },
          kanaReading: { type: Type.STRING },
          hangulReading: { type: Type.STRING },
          meaning: { type: Type.STRING },
          example: { type: Type.STRING },
          level: { type: Type.STRING },
        },
        required: ["id", "word", "kanaReading", "hangulReading", "meaning", "example", "level"]
      }
    }
  };

  const candidateModels = ["gemini-3-flash-preview", "gemini-2.5-flash"];
  let lastError: unknown = null;
  for (const model of candidateModels) {
    try {
      const response = await ai.models.generateContent({ model, contents: prompt, config });
      const text = response.text || "[]";
      try {
        return JSON.parse(text) as KanjiItem[];
      } catch (parseError) {
        throw new Error(`응답 파싱 실패 (${model}): ${text.slice(0, 120)}`);
      }
    } catch (e) {
      lastError = e;
    }
  }
  const msg = lastError instanceof Error ? lastError.message : String(lastError);
  throw new Error(msg || "Gemini 호출 실패");
}
