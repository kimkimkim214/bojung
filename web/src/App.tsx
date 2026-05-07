/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useRef, useCallback, FormEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  BookOpen, 
  CheckCircle2, 
  XCircle, 
  RefreshCcw, 
  ChevronRight, 
  Award, 
  BrainCircuit,
  GraduationCap,
  Sparkles,
  Search,
  BookMarked,
  X
} from 'lucide-react';
import { KanjiItem, AppPhase, StudyMode } from './types';
import { fetchKanjiSet, getApiKey, setApiKey, getDefaultApiKey } from './services/geminiService';

export default function App() {
  const [phase, setPhase] = useState<AppPhase>('landing');
  const [mode, setMode] = useState<StudyMode>('vocab');
  const [level, setLevel] = useState('N5');
  const [kanjiList, setKanjiList] = useState<KanjiItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [userInput, setUserInput] = useState('');
  const [feedback, setFeedback] = useState<'none' | 'correct' | 'wrong'>('none');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionCount, setSessionCount] = useState(0);
  const [studyPool, setStudyPool] = useState<KanjiItem[]>([]);
  const [correctStreak, setCorrectStreak] = useState<Record<string, number>>({});
  const [isReviewOpen, setIsReviewOpen] = useState(false); 
  const [masteredItems, setMasteredItems] = useState<Record<string, KanjiItem>>({});
  const [isMasteredListOpen, setIsMasteredListOpen] = useState(false);
  const [memoTab, setMemoTab] = useState<'current' | 'saved'>('current');
  
  const inputRef = useRef<HTMLInputElement>(null);

  const [isApiKeyOpen, setIsApiKeyOpen] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [apiKeySaved, setApiKeySaved] = useState(false);

  useEffect(() => {
    setApiKeyInput(getApiKey());
  }, [isApiKeyOpen]);

  const handleSaveApiKey = () => {
    setApiKey(apiKeyInput);
    setApiKeySaved(true);
    setTimeout(() => setApiKeySaved(false), 1500);
  };

  const handleResetApiKey = () => {
    setApiKey('');
    setApiKeyInput(getDefaultApiKey());
    setApiKeySaved(true);
    setTimeout(() => setApiKeySaved(false), 1500);
  };

  // Load mastered items from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('mastered_kanji_items');
    if (saved) {
      try {
        setMasteredItems(JSON.parse(saved));
      } catch (e) {
        console.error('Failed to parse mastered items', e);
      }
    }
  }, []);

  // Save mastered items to localStorage when changed
  useEffect(() => {
    localStorage.setItem('mastered_kanji_items', JSON.stringify(masteredItems));
  }, [masteredItems]);

  const toggleMastered = (item: KanjiItem) => {
    setMasteredItems(prev => {
      const next = { ...prev };
      if (next[item.word]) {
        delete next[item.word];
      } else {
        next[item.word] = item;
      }
      return next;
    });
  };

  // Load initial set
  const startStudy = async (selectedLevel: string, selectedMode: StudyMode) => {
    setIsLoading(true);
    setLevel(selectedLevel);
    setMode(selectedMode);
    // Include current mastered words to exclude them from the new set
    const excludeWords = (Object.values(masteredItems) as KanjiItem[]).map(k => k.word);
    const set = await fetchKanjiSet(selectedLevel, selectedMode, 10, excludeWords);
    // Double-check and filter out any leaking mastered items
    const filteredSet = set.filter(item => !masteredItems[item.word]);
    if (filteredSet.length > 0) {
      setKanjiList(filteredSet);
      setStudyPool([...filteredSet]);
      setCurrentIndex(0);
      setPhase('study');
      setSessionCount(0);
      setCorrectStreak({});
      setMemoTab('current');
      setIsReviewOpen(false);
      setIsMasteredListOpen(true); // Automatically open the floating pad
    }
    setIsLoading(false);
  };

  const nextSet = async () => {
    setIsLoading(true);
    // Exclude current list AND all mastered items globally
    const excludeWords = [...kanjiList.map(k => k.word), ...(Object.values(masteredItems) as KanjiItem[]).map(k => k.word)];
    const set = await fetchKanjiSet(level, mode, 10, excludeWords);
    // Double-check and filter out any leaking mastered items
    const filteredSet = set.filter(item => !masteredItems[item.word]);
    if (filteredSet.length > 0) {
      setKanjiList(filteredSet);
      setStudyPool([...filteredSet]);
      setCurrentIndex(0);
      setFeedback('none');
      setUserInput('');
      setSessionCount(0);
      setCorrectStreak({});
      setMemoTab('current');
      setIsReviewOpen(false);
      setIsMasteredListOpen(true); // Automatically open the floating pad for the new set
    }
    setIsLoading(false);
  };

  const currentItem = studyPool[currentIndex];

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    
    // If feedback is already shown, Enter moves to the next word
    if (feedback !== 'none') {
      handleNext();
      return;
    }

    if (!currentItem) return;

    // Normalize: remove spaces, special characters, and common suffixes
    const normalize = (str: string | undefined) => {
      if (!str) return '';
      let res = str.trim()
        .replace(/\s+/g, '')
        .replace(/-/g, '')
        .replace(/ー/g, '')
        .replace(/\([^)]*\)/g, ''); 
      
      if (mode === 'radical' || mode === 'kanji') {
        // Remove common naming suffixes to allow just the base name/meaning
        res = res.replace(/(변|방|머리|발|엄|받침|갓|밑|몸|옆|자|부|편)$/g, '');
      }
      return res;
    };
    
    const cleanInput = normalize(userInput);
    const canonicalReading = normalize(currentItem.hangulReading);
    const canonicalMeaning = normalize(currentItem.meaning);
    
    let isCorrect = false;
    if (mode === 'vocab') {
      isCorrect = 
        (cleanInput.includes(canonicalReading) && cleanInput.includes(canonicalMeaning)) ||
        (cleanInput === canonicalReading + canonicalMeaning) ||
        (cleanInput === canonicalMeaning + canonicalReading);
    } else {
      // For Kanji or Radicals, either reading OR meaning is fine, 
      // or a combination, and we use fuzzy search principles
      isCorrect = cleanInput === canonicalReading || 
                  cleanInput === canonicalMeaning || 
                  cleanInput === canonicalMeaning + canonicalReading ||
                  (canonicalReading.includes(cleanInput) && cleanInput.length >= 2);
    }

    if (isCorrect) {
      setFeedback('correct');
      setSessionCount(prev => prev + 1);
      
      // If correct, increment streak but DO NOT automatically master
      const newStreak = (correctStreak[currentItem.word] || 0) + 1;
      setCorrectStreak(prev => ({
        ...prev,
        [currentItem.word]: newStreak
      }));
    } else {
      setFeedback('wrong');
    }
  };

  const handleNext = useCallback(() => {
    setFeedback('none');
    setUserInput('');
    
    // Move to next in pool or reshuffle if end reached
    if (studyPool.length > 0) {
      const nextIdx = (currentIndex + 1) % studyPool.length;
      // If we finished a cycle, maybe shuffle?
      if (nextIdx === 0) {
        setStudyPool(prev => [...prev].sort(() => Math.random() - 0.5));
      }
      setCurrentIndex(nextIdx);
    }
  }, [currentIndex, studyPool.length]);

  useEffect(() => {
    if (phase === 'study' && feedback === 'none') {
      // Use a small timeout to ensure DOM is updated and ready for focus
      const timer = setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
        }
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [phase, feedback, currentIndex, isMasteredListOpen]);

  const landingContent = (
    <div className="min-h-screen bg-[#F5F5F0] flex flex-col items-center justify-center p-6 font-sans">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-[420px] text-center space-y-10"
      >
        <div className="space-y-3">
          <h1 className="text-6xl font-black tracking-tighter text-[#141414]">
            言言日本語
          </h1>
          <p className="text-[#5A5A40] text-xl italic serif opacity-80">
            언제 어디서나, 단어 한 마디씩
          </p>
        </div>

        <div className="bg-white p-10 rounded-[48px] shadow-[0_10px_40px_rgba(0,0,0,0.04)] border border-[#E4E3E0] space-y-10">
          <div className="space-y-5">
            <p className="text-[10px] font-black text-[#5A5A40] uppercase tracking-[0.3em] opacity-60">모드 선택</p>
            <div className="flex flex-col gap-3">
              {(['vocab', 'kanji', 'radical'] as StudyMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`w-full py-5 rounded-[24px] font-black transition-all ${mode === m ? 'bg-[#141414] text-white shadow-xl scale-[1.02]' : 'bg-[#F5F5F0] text-[#888] hover:text-[#141414] border border-transparent hover:border-[#E4E3E0]'}`}
                >
                  {m === 'vocab' ? '단어 (Vocab)' : m === 'kanji' ? '한자 (Kanji)' : '부수 (Radical)'}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <p className="text-[10px] font-black text-[#5A5A40] uppercase tracking-[0.3em] opacity-60">난이도 선택</p>
            {mode === 'vocab' ? (
              <div className="grid grid-cols-5 gap-3">
                {['N5', 'N4', 'N3', 'N2', 'N1'].map((lv) => (
                  <button
                    key={lv}
                    id={`btn-level-${lv}`}
                    onClick={() => startStudy(lv, mode)}
                    disabled={isLoading}
                    className="aspect-[3/4] flex items-center justify-center rounded-2xl border-2 border-[#E4E3E0] hover:border-[#141414] hover:bg-[#141414] hover:text-white transition-all font-black disabled:opacity-50"
                  >
                    {lv}
                  </button>
                ))}
              </div>
            ) : (
              <button
                onClick={() => startStudy('General', mode)}
                disabled={isLoading}
                className="w-full bg-[#141414] text-white py-6 rounded-[28px] font-black text-xl hover:scale-[1.02] active:scale-[0.98] transition-all shadow-2xl flex items-center justify-center gap-3"
              >
                <BrainCircuit size={28} />
                학습 시작하기
              </button>
            )}
          </div>

          <p className="text-[#888] text-sm italic">
            {mode === 'vocab' 
              ? 'JLPT 급수별 필수 단어를 학습합니다.' 
              : mode === 'kanji' 
              ? '일본 상용 한자의 한글 훈음을 학습합니다.'
              : '한자의 기초가 되는 214개 부수를 학습합니다.'}
          </p>

          {Object.keys(masteredItems).length > 0 && (
            <div className="pt-4 border-t border-[#F5F5F0]">
              <button
                onClick={() => setIsMasteredListOpen(true)}
                className="text-xs font-bold text-[#5A5A40] flex items-center justify-center gap-2 hover:text-[#141414] transition-colors mx-auto"
              >
                <CheckCircle2 size={14} className="text-[#22C55E]" />
                마스터한 {Object.keys(masteredItems).length}개 단어 보기
              </button>
            </div>
          )}

          <div className="pt-4 border-t border-[#F5F5F0]">
            <button
              onClick={() => setIsApiKeyOpen(true)}
              className="text-xs font-bold text-[#5A5A40] flex items-center justify-center gap-2 hover:text-[#141414] transition-colors mx-auto"
            >
              <Sparkles size={14} className="text-[#5A5A40]" />
              Gemini API 키 설정
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );

  const apiKeyModal = (
    <AnimatePresence>
      {isApiKeyOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsApiKeyOpen(false)}
            className="fixed inset-0 z-[80] bg-black/40 backdrop-blur-sm"
          />
          <div className="fixed inset-0 z-[85] flex items-center justify-center p-4 pointer-events-none">
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 30 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 30 }}
              className="bg-white w-full max-w-md p-8 rounded-[32px] shadow-2xl pointer-events-auto border border-[#E4E3E0] space-y-5"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-black text-[#141414] uppercase tracking-tight">Gemini API 키</h3>
                <button
                  onClick={() => setIsApiKeyOpen(false)}
                  className="p-1 hover:bg-[#F5F5F0] rounded-full text-[#141414]"
                >
                  <X size={22} />
                </button>
              </div>
              <p className="text-xs text-[#888] leading-relaxed">
                키를 비워두고 저장하면 기본 키가 사용됩니다. 변경한 키는 이 기기에만 저장됩니다.
              </p>
              <input
                type="text"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder="AIzaSy..."
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                className="w-full bg-[#F5F5F0] border-2 border-[#E4E3E0] rounded-2xl px-5 py-4 text-sm font-mono focus:border-[#141414] focus:outline-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleResetApiKey}
                  className="flex-1 bg-[#F5F5F0] text-[#141414] py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-[#E4E3E0] transition-all"
                >
                  기본값
                </button>
                <button
                  onClick={handleSaveApiKey}
                  className="flex-[2] bg-[#141414] text-white py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:scale-[1.02] active:scale-[0.98] transition-all"
                >
                  {apiKeySaved ? '저장됨 ✓' : '저장'}
                </button>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );

  const mainContent = (
    <div className="min-h-screen bg-[#F5F5F0] flex flex-col p-6 md:p-10 font-sans items-center">
      {/* Header */}
      <header className="w-full max-w-[420px] flex justify-between items-center mb-10">
        <button 
          onClick={() => setPhase('landing')}
          className="text-[#5A5A40] flex items-center gap-2 hover:text-[#141414] transition-colors"
        >
          <BookOpen size={20} />
          <span className="font-black uppercase tracking-[0.2em] text-[10px]">Menu</span>
        </button>
        
            <div className="flex items-center gap-2">
              <button 
                onClick={() => {
                  setMemoTab('saved');
                  setIsMasteredListOpen(true);
                }}
                className="bg-white px-4 py-2.5 rounded-full border border-[#E4E3E0] flex items-center gap-3 shadow-sm hover:border-[#141414] transition-all"
              >
                <CheckCircle2 size={16} className="text-[#22C55E]" />
                <span className="text-[11px] font-black text-[#141414]">{Object.keys(masteredItems).length}</span>
              </button>
              <div className="bg-white px-4 py-2.5 rounded-full border border-[#E4E3E0] flex items-center gap-3 shadow-sm">
                <Award size={16} className="text-[#5A5A40]" />
                <span className="text-[11px] font-black text-[#141414]">
                  {mode === 'vocab' ? `${level} · ` : ''}
                  {mode === 'vocab' ? '단어' : mode === 'kanji' ? '한자' : '부수'}
                </span>
              </div>
            </div>
      </header>

      {/* Main Study Area */}
      <main className="w-full max-w-[420px] flex-1 flex flex-col shrink-0">
        <AnimatePresence mode="wait">
          {isLoading ? (
            <motion.div 
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col items-center justify-center space-y-6"
            >
              <RefreshCcw className="animate-spin text-[#5A5A40]" size={56} />
              <p className="text-[#5A5A40] font-black italic tracking-tight">AI 큐레이션 중...</p>
            </motion.div>
          ) : (
            <motion.div 
              key={`item-${currentItem?.word}`}
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              className="flex-1 flex flex-col space-y-10"
            >
              <div className="flex justify-start">
                <button 
                  onClick={() => {
                    setMemoTab('current');
                    setIsMasteredListOpen(true);
                  }}
                  className="text-[10px] font-black text-[#5A5A40] flex items-center gap-2 hover:text-[#141414] bg-white px-4 py-2 rounded-full border border-[#E4E3E0] shadow-sm uppercase tracking-widest"
                >
                  <Search size={14} /> 메모장 보기
                </button>
              </div>
              {/* Kanji Card - Taller for Note 20 feel */}
              <div className="bg-white rounded-[48px] p-12 shadow-[0_20px_50px_rgba(0,0,0,0.05)] border border-[#E4E3E0] flex flex-col items-center justify-center relative overflow-hidden min-h-[420px]">
                <div className="absolute top-8 left-10 flex items-center gap-2 flex-wrap pr-32">
                  {Array.from({ length: studyPool.length }).map((_, i) => (
                    <div 
                      key={i}
                      className={`h-1.5 w-5 md:w-7 rounded-full transition-all ${
                        i === currentIndex ? 'bg-[#141414] w-8 md:w-12 shadow-sm' : 'bg-[#E4E3E0]'
                      }`}
                    />
                  ))}
                </div>

                {/* Feedback Badge */}
                <AnimatePresence>
                  {feedback !== 'none' && (
                    <motion.div 
                      initial={{ opacity: 0, scale: 0.5, y: -20 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      className="absolute top-8 right-10"
                    >
                      {feedback === 'correct' ? (
                        <div className="flex items-center gap-2 bg-[#22C55E] text-white px-5 py-2.5 rounded-full font-black shadow-lg">
                          <CheckCircle2 size={20} />
                          <span className="text-xs uppercase tracking-widest">Pass</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 bg-[#FF4B4B] text-white px-5 py-2.5 rounded-full font-black shadow-lg">
                          <XCircle size={20} />
                          <span className="text-xs uppercase tracking-widest">Fail</span>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="text-center space-y-6">
                  <h2 className="text-[100px] md:text-[120px] font-black leading-none text-[#141414] select-none break-all px-4 tracking-tighter">
                    {currentItem?.word}
                  </h2>
                  <div className="h-10">
                    {feedback !== 'none' && (
                      <motion.div 
                        initial={{ opacity: 0, y: 15 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="space-y-1"
                      >
                        <p className="text-2xl font-black text-[#5A5A40]">
                          {currentItem?.hangulReading}
                        </p>
                        <p className="text-sm font-bold text-[#888] italic">
                          {currentItem?.kanaReading}
                        </p>
                      </motion.div>
                    )}
                  </div>
                </div>
              </div>

              {/* Input Area */}
              <div className="space-y-6">
                <form onSubmit={handleSubmit} className="relative">
                  <input
                    ref={inputRef}
                    type="text"
                    id="input-answer"
                    placeholder={mode === 'vocab' ? "발음 + 의미 입력 (니치 날)" : mode === 'kanji' ? "훈음 입력 (날 일)" : "부수 입력"}
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    readOnly={feedback !== 'none'}
                    className={`w-full bg-white border-3 border-[#E4E3E0] rounded-[28px] px-8 py-7 text-2xl font-black focus:border-[#141414] focus:outline-none transition-all placeholder:text-[#BBB] placeholder:text-lg ${feedback !== 'none' ? 'cursor-default opacity-80' : 'shadow-xl focus:shadow-2xl'}`}
                    autoComplete="off"
                  />
                  <div className="absolute right-5 top-1/2 -translate-y-1/2 flex items-center gap-3">
                    {feedback === 'none' ? (
                      <button 
                        type="submit"
                        id="btn-submit"
                        className="bg-[#141414] text-white p-3 rounded-[20px] hover:scale-110 active:scale-90 transition-all shadow-lg"
                      >
                        <ChevronRight size={32} />
                      </button>
                    ) : (
                      <button 
                        type="button"
                        id="btn-next"
                        onClick={handleNext}
                        className="bg-[#141414] text-white px-6 py-4 rounded-[22px] flex items-center gap-3 font-black text-sm uppercase tracking-widest hover:scale-105 active:scale-95 transition-all shadow-xl"
                      >
                        NEXT
                        <ChevronRight size={22} />
                      </button>
                    )}
                  </div>
                </form>

                <AnimatePresence>
                  {feedback === 'wrong' && (
                    <motion.div 
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="bg-red-50 border border-red-100 p-6 rounded-[28px] text-red-600 text-center"
                    >
                      <p className="text-xs font-black uppercase tracking-widest mb-2 opacity-50">정답 확인</p>
                      <p className="text-xl font-black">{currentItem.hangulReading} ({currentItem.meaning})</p>
                    </motion.div>
                  )}

                  {feedback === 'correct' && (
                    <motion.div 
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="bg-green-50 border border-green-100 p-6 rounded-[28px] text-green-700 space-y-3"
                    >
                      <div className="flex items-center justify-center gap-2 font-black text-lg uppercase tracking-widest">
                         Excellence! ✨
                      </div>
                      <p className="text-center text-sm font-medium leading-relaxed opacity-80 italic">"{currentItem.example}"</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Progress Summary */}
              <div className="pt-6 flex flex-col items-center space-y-6">
                <div className="flex gap-4 w-full">
                  <div className="flex-1 bg-white p-6 rounded-[32px] border border-[#E4E3E0] shadow-sm flex flex-col items-center gap-1">
                    <p className="text-[10px] font-black text-[#888] uppercase tracking-[0.2em]">SESSIONS</p>
                    <p className="text-2xl font-black text-[#141414]">{sessionCount}</p>
                  </div>
                  <div className="flex-1 bg-white p-6 rounded-[32px] border border-[#E4E3E0] shadow-sm flex flex-col items-center gap-1">
                    <p className="text-[10px] font-black text-[#888] uppercase tracking-[0.2em]">PROGRESS</p>
                    <p className="text-2xl font-black text-[#141414]">
                      {Object.values(correctStreak).filter((s: number) => s >= 2).length} / 10
                    </p>
                  </div>
                </div>

                <button 
                  id="btn-next-set"
                  onClick={nextSet}
                  disabled={isLoading}
                  className="w-full bg-[#5A5A40] text-white py-6 rounded-[28px] font-black uppercase tracking-[0.2em] text-sm hover:bg-[#4A4A30] transition-all flex items-center justify-center gap-3 disabled:opacity-50 shadow-lg hover:shadow-xl active:scale-[0.98]"
                >
                  <RefreshCcw size={20} />
                  Complete & Next Set
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Footer */}
      <footer className="mt-8 text-center text-[#9e9e9e] text-xs font-medium tracking-tight">
        © 2024 言言日本語 • AI STUDY COMPANION
      </footer>
    </div>
  );

  return (
    <>
      {phase === 'landing' ? landingContent : mainContent}
      {apiKeyModal}

      {/* Floating Memo Toggle Button */}
      <button 
        onClick={() => {
          setMemoTab('saved');
          setIsMasteredListOpen(!isMasteredListOpen);
        }}
        className="fixed bottom-8 right-8 z-[70] w-14 h-14 bg-[#141414] text-white rounded-full shadow-2xl flex items-center justify-center hover:scale-110 active:scale-95 transition-all group"
      >
        <div className="relative">
          <BookMarked size={24} />
          {Object.keys(masteredItems).length > 0 && (
            <span className="absolute -top-3 -right-3 bg-[#FF4B4B] text-white text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center border-2 border-white">
              {Object.keys(masteredItems).length}
            </span>
          )}
        </div>
      </button>

      {/* Centered Memo Pad Modal */}
      <AnimatePresence>
        {isMasteredListOpen && (
          <>
            {/* Centered Modal Backdrop */}
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsMasteredListOpen(false)}
              className="fixed inset-0 z-[55] bg-black/40 backdrop-blur-sm"
            />
            
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 pointer-events-none">
              <motion.div 
                initial={{ opacity: 0, scale: 0.9, y: 30 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 30 }}
                className="bg-white w-full max-w-2xl h-[700px] max-h-[85vh] shadow-[0_40px_100px_rgba(0,0,0,0.4)] relative z-10 flex flex-col overflow-hidden pointer-events-auto rounded-[40px] border border-[#E4E3E0]"
              >
                {/* Pad Header */}
                <div className="pt-8 px-8 pb-6 border-b border-[#F5F5F0] bg-[#FCFCFA]">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <div className="w-3.5 h-3.5 rounded-full bg-[#FF4B4B] shadow-[0_0_12px_rgba(255,75,75,0.4)]" />
                      <h2 className="text-xl font-black text-[#141414] uppercase tracking-tight">AI 단어 메모장</h2>
                    </div>
                    <button 
                      onClick={() => setIsMasteredListOpen(false)}
                      className="p-2 hover:bg-[#F5F5F0] rounded-full transition-colors text-[#141414]"
                    >
                      <X size={24} />
                    </button>
                  </div>
                  
                  {/* Tabs */}
                  <div className="flex gap-2 p-1.5 bg-[#F5F5F0] rounded-2xl border border-[#E4E3E0]">
                    <button
                      onClick={() => setMemoTab('current')}
                      className={`flex-1 py-3 text-xs font-black rounded-xl transition-all ${memoTab === 'current' ? 'bg-white text-[#141414] shadow-md' : 'text-[#888]'}`}
                    >
                      현재 학습 중 ({kanjiList.length})
                    </button>
                    <button
                      onClick={() => setMemoTab('saved')}
                      className={`flex-1 py-3 text-xs font-black rounded-xl transition-all ${memoTab === 'saved' ? 'bg-white text-[#141414] shadow-md' : 'text-[#888]'}`}
                    >
                      나의 저장소 ({Object.keys(masteredItems).length})
                    </button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto p-6 custom-scrollbar bg-[#FDFDFB]">
                  {memoTab === 'current' ? (
                    <div className="grid gap-3">
                      {kanjiList.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-center py-20 opacity-30">
                          <Search size={48} className="mb-4" />
                          <p className="text-sm font-bold">아직 단어 뭉치를 가져오지 않았습니다.</p>
                        </div>
                      ) : (
                        kanjiList.map((item) => {
                          const isMastered = !!masteredItems[item.word];
                          return (
                            <div 
                              key={item.word} 
                              className={`flex items-center justify-between p-5 rounded-[24px] border transition-all ${
                                isMastered ? 'bg-[#F5F5F0] border-transparent opacity-60' : 'bg-white border-[#F0F0EE] shadow-sm'
                              }`}
                            >
                              <div className="flex items-center gap-5">
                                <span className={`text-4xl font-bold transition-colors ${isMastered ? 'text-[#888]' : 'text-[#141414]'}`}>{item.word}</span>
                                <div>
                                  <p className={`text-sm font-semibold mb-1 ${isMastered ? 'text-[#888]' : 'text-[#5A5A40]'}`}>{item.hangulReading} ({item.kanaReading})</p>
                                  <p className="text-base font-medium text-[#888]">{item.meaning}</p>
                                </div>
                              </div>
                              <button
                                onClick={() => toggleMastered(item)}
                                className={`p-3 rounded-xl transition-all ${
                                  isMastered ? 'bg-[#141414] text-white' : 'bg-white border border-[#E4E3E0] text-[#DDD] hover:text-[#22C55E] hover:border-[#22C55E]'
                                }`}
                                title="이미 아는 단어"
                              >
                                <CheckCircle2 size={24} />
                              </button>
                            </div>
                          );
                        })
                      )}
                    </div>
                  ) : (
                    <div className="grid gap-3">
                      {Object.keys(masteredItems).length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-center py-20 opacity-30">
                          <BookMarked size={48} className="mb-4" />
                          <p className="text-sm font-bold">저장된 단어가 없습니다.</p>
                        </div>
                      ) : (
                        (Object.values(masteredItems) as KanjiItem[]).map((item) => (
                          <div 
                            key={item.word} 
                            className="flex items-center justify-between p-5 bg-white rounded-[24px] border border-[#F0F0EE] hover:border-[#141414] transition-all group shadow-sm"
                          >
                            <div className="flex items-center gap-5">
                              <span className="text-4xl font-bold text-[#141414]">{item.word}</span>
                              <div>
                                <p className="text-sm font-semibold text-[#5A5A40] mb-1">{item.hangulReading} ({item.kanaReading})</p>
                                <p className="text-base font-medium text-[#888]">{item.meaning}</p>
                              </div>
                            </div>
                            <button
                              onClick={() => toggleMastered(item)}
                              className="flex-shrink-0 p-3 text-[#EEE] hover:text-[#FF4B4B] transition-colors bg-[#FDFDFB] rounded-xl border border-[#F5F5F0]"
                              title="삭제"
                            >
                              <X size={20} />
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
                
                <div className="p-8 border-t border-[#F5F5F0] bg-white">
                  <button 
                    onClick={() => setIsMasteredListOpen(false)}
                    className="w-full bg-[#141414] text-white py-5 rounded-2xl font-black text-sm uppercase tracking-[0.2em] hover:bg-black transition-all hover:scale-[1.01] active:scale-[0.99] shadow-xl"
                  >
                    메모장 닫기
                  </button>
                </div>
              </motion.div>
            </div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
