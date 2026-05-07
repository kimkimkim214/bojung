import { KanjiItem, StudyMode } from "../types";
import { radicals } from "../data/radicals";
import { kanjiList } from "../data/kanji";
import { vocabByLevel } from "../data/vocab";

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function pool(level: string, mode: StudyMode): KanjiItem[] {
  if (mode === "vocab") return vocabByLevel[level] ?? vocabByLevel.N5;
  if (mode === "kanji") return kanjiList;
  return radicals;
}

export async function fetchKanjiSet(
  level: string = "N5",
  mode: StudyMode = "vocab",
  count: number = 10,
  excludeWords: string[] = [],
): Promise<KanjiItem[]> {
  const exclude = new Set(excludeWords);
  const candidates = pool(level, mode).filter((item) => !exclude.has(item.word));
  if (candidates.length === 0) {
    throw new Error(
      `이 모드/레벨에서 학습 가능한 항목이 모두 마스터되었거나 데이터가 없습니다. 메모장에서 마스터를 일부 해제하거나 다른 모드/레벨을 선택하세요.`,
    );
  }
  return shuffle(candidates).slice(0, count);
}
