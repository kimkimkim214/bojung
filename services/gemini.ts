import { GoogleGenAI } from "@google/genai";

const getGeminiClient = () => {
  let processEnvApi = '';
  let processEnvGemini = '';
  try {
    if (typeof process !== 'undefined' && process.env) {
      processEnvApi = process.env.API_KEY || '';
      processEnvGemini = process.env.GEMINI_API_KEY || '';
    }
  } catch(e) {}

  let apiKey = '';
  try {
     apiKey = (import.meta as any).env?.VITE_GEMINI_API_KEY || processEnvApi || processEnvGemini;
  } catch(e) {
     apiKey = processEnvApi || processEnvGemini;
  }

  if (!apiKey) {
    throw new Error("API Key not found in environment variables");
  }
  return new GoogleGenAI({ apiKey });
};

// data URL → { mimeType, data } 변환 헬퍼
// - image/* 면 그대로 사용
// - application/octet-stream 등 잘못된 MIME 이 박혀있어도 base64 부분만 떼서 image/png 로 보냄
// - data URL 이 아니면 이미 순수 base64 라고 간주
const toInlinePart = (img: string) => {
  const m = img.match(/^data:([^;,]+);base64,(.+)$/);
  if (m) {
    const mime = m[1].startsWith('image/') ? m[1] : 'image/png';
    return { inlineData: { mimeType: mime, data: m[2] } };
  }
  // data URL 이 아니면 순수 base64 로 간주 (data URL prefix 가 섞여있으면 절대 안됨)
  if (img.startsWith('data:')) {
    // base64 부분만 추출 시도
    const comma = img.indexOf(',');
    if (comma >= 0) {
      return { inlineData: { mimeType: 'image/png', data: img.slice(comma + 1) } };
    }
  }
  return { inlineData: { mimeType: 'image/jpeg', data: img } };
};

const getAspectRatio = (dataUrl: string): Promise<string> =>
  new Promise((resolve) => {
    if (typeof Image === 'undefined') return resolve("1:1");
    const img = new Image();
    img.onload = () => {
      const r = img.naturalWidth / img.naturalHeight;
      const candidates: Array<[string, number]> = [
        ["1:1",  1.0],
        ["4:3",  4/3],
        ["3:4",  3/4],
        ["16:9", 16/9],
        ["9:16", 9/16],
      ];
      const best = candidates.reduce((a, b) =>
        Math.abs(b[1] - r) < Math.abs(a[1] - r) ? b : a
      );
      resolve(best[0]);
    };
    img.onerror = () => resolve("1:1");
    img.src = dataUrl;
  });

export const analyzeReferenceImages = async (
  images: string[],
  context: 'face' | 'outfit' | 'manga-style' | 'appearance-style'
): Promise<string> => {
  const ai = getGeminiClient();
  const parts = images.map(toInlinePart);

  let prompt = "";
  if (context === 'face') {
    prompt = "Analyze the facial features, hairstyle, and expression of the person in these images. Provide highly descriptive keywords and phrases. Focus on: face shape, eye shape/color, nose profile, lip shape, hair texture/length/color, and any identifying marks. Use professional character design terminology. MUST BE IN KOREAN (한국어로 출력해줘).";
  } else if (context === 'outfit') {
    prompt = "Analyze the clothing, accessories, footwear, and overall silhouette in these images. Provide descriptive keywords. Focus on: fabric type, garment construction (e.g., 'tailored blazer', 'oversized hoodie'), specific colors, patterns, and layered elements. MUST BE IN KOREAN (한국어로 출력해줘).";
  } else if (context === 'appearance-style') {
    prompt = "Analyze the overall character appearance, vibe, and facial stylization in these images. Provide highly descriptive keywords. Focus on: general atmosphere, eye stylization, character proportions, and distinct aesthetic elements (e.g. sharp, cute, delicate). MUST BE IN KOREAN (한국어로 출력해줘).";
  } else {
    prompt = "Analyze the drawing style of these manga illustration samples. Provide highly descriptive keywords focusing on: line thickness and quality (e.g., crisp, sketchy, brush-like), use of screentones (density, patterns), shading techniques (cross-hatching, solid blacks), and overall aesthetic mood. MUST BE IN KOREAN (한국어로 출력해줘).";
  }

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3.1-pro-preview',
      contents: { parts: [...parts, { text: prompt }] }
    });
    return response.text || "";
  } catch (error: any) {
    console.error("Gemini Analysis Error:", error);
    throw new Error(error.message || "Failed to analyze image.");
  }
};

export interface CharacterInput {
  name: string;
  color: 'red' | 'blue' | 'green' | 'amber';
  height?: string;
  weight?: string;
  bodyType?: string;
  facePrompt: string;
  outfitPrompt: string;
  faceImages?: string[];
  outfitImages?: string[];
}

export interface ModelInputs {
  imageBase64: string;          // 스케치 (콘티)
  userPrompt: string;
  styleImages?: string[];
  styleFeatures?: string;
  physical?: {
    windStrength: number;
    windDirection: string;
    gravityEnabled: boolean;
  };
  characters: CharacterInput[];
}

export interface MangaInputs {
  imageBase64: string;          // 3D 피규어 이미지
  userPrompt: string;
  styleImages?: string[];       // 만화 선화 스타일 레퍼런스
  styleFeatures?: string;       // 추출된 스타일 특징
  characters: CharacterInput[];
}

export const generateMangaArt = async (inputs: MangaInputs): Promise<string> => {
  const ai = getGeminiClient();
  const { imageBase64, userPrompt, styleImages, styleFeatures, characters } = inputs;

  const baseImagePart = toInlinePart(imageBase64);

  const STYLE_LIMIT = 5;
  const styleParts = (styleImages || []).slice(0, STYLE_LIMIT).map(toInlinePart);

  const hasStyleRef = styleParts.length > 0;

  // Characters references (collecting images for each)
  const faceParts: any[] = [];
  const outfitParts: any[] = [];
  (characters || []).forEach(char => {
    (char.faceImages || []).slice(0, 2).forEach(img => faceParts.push(toInlinePart(img)));
    (char.outfitImages || []).slice(0, 2).forEach(img => outfitParts.push(toInlinePart(img)));
  });

  let inputRoster = `INPUT IMAGES:\n`;
  let idx = 1;
  const TOTAL_FACE = faceParts.length;
  const TOTAL_OUTFIT = outfitParts.length;
  const TOTAL_STYLE = styleParts.length;

  if (TOTAL_STYLE > 0) {
    inputRoster += `  - Images ${idx}–${idx + TOTAL_STYLE - 1}: MANGA STYLE REFERENCE.\n`;
    idx += TOTAL_STYLE;
  }
  if (TOTAL_FACE > 0) {
    inputRoster += `  - Images ${idx}–${idx + TOTAL_FACE - 1}: FACE REFERENCES for characters.\n`;
    idx += TOTAL_FACE;
  }
  if (TOTAL_OUTFIT > 0) {
    inputRoster += `  - Images ${idx}–${idx + TOTAL_OUTFIT - 1}: OUTFIT REFERENCES for characters.\n`;
    idx += TOTAL_OUTFIT;
  }
  inputRoster += `  - Image ${idx}: 3D BASE MODEL (Source of pose and layout).`;

  let characterDetails = (characters || []).map(c => {
    let physText = [];
    if (c.height) physText.push(`Height: ${c.height}`);
    if (c.weight) physText.push(`Weight: ${c.weight}`);
    if (c.bodyType) physText.push(`Physique: ${c.bodyType}`);
    const physStr = physText.length > 0 ? ` Physical attributes: ${physText.join(', ')}.` : '';
    return `- Character "${c.name}": Mapping to the figure in the 3D model that matches this character's identity.${physStr} Features: ${c.facePrompt}. Outfit: ${c.outfitPrompt}.`;
  }).join('\n');

  let styleInstruction = "Traditional Japanese manga pen-and-ink style (black and white, screentones).";
  if (styleFeatures) {
    styleInstruction += ` Specific style features to follow: ${styleFeatures}`;
  }

  const systemPrompt = `
    Transform the provided 3D model image into a high-quality traditional Japanese manga panel line art illustration.

    ${inputRoster}

    PRIORITY ORDER (ABSOLUTE — DO NOT DEVIATE):
    1. STORYBOARD GEOMETRY LOCK — Image ${idx} is the ground truth for ALL of the following.
       You MUST replicate, not reinterpret:
       a. ASPECT RATIO & CROP: Output canvas matches the 3D base model's frame exactly.
          The edges of the 3D base model ARE the edges of the output.
       b. SHOT SIZE: If the 3D base model shows a close-up (face/upper body only), the output
          is a close-up. If it shows a wide shot, the output is a wide shot.
          NEVER expand the framing to show more of the body than the 3D base model shows.
          NEVER zoom in or out from what the 3D base model depicts.
       c. CAMERA ANGLE: Eye-level / high-angle / low-angle / Dutch — match it precisely.
       d. COMPOSITION: Subject placement within the frame (rule-of-thirds positions,
          headroom, lead room, negative space) is preserved.
       e. POSE & MOTION: Body axis, limb angles, weight distribution, motion lines,
          and silhouette dynamics are preserved. Do not "fix" or "neutralize" an exaggerated pose.
       f. SILHOUETTE / FORM: The overall shape of each subject within the frame matches
          the 3D base model's silhouette.

    2. CHARACTER MAPPING:
    ${characterDetails}

    3. MANGA AESTHETIC & STYLE MATCH: ${hasStyleRef ? "Match the precise inking and line weight of the STYLE REFERENCE images." : "Use a clean, modern manga style."}

    EXPLICIT OVERRIDES:
    - Black and white ONLY (with grays/tones).
    - ${styleInstruction}

    WHAT TO IGNORE FROM THE 3D BASE MODEL (and ONLY these):
    - Generic placeholder faces and clothing drawn on the figures.
    EVERYTHING ELSE in the 3D BASE MODEL — frame edges, pose, scale within frame, angle, silhouette — is BINDING.

    User Instruction: "${userPrompt ? userPrompt : "Convert this 3D scene into a Manga panel illustration."}"
  `;

  try {
    const aspectRatio = await getAspectRatio(imageBase64);

    const response = await ai.models.generateContent({
      model: 'gemini-3.1-flash-image-preview',
      config: {
        imageConfig: {
          aspectRatio: aspectRatio,
          imageSize: "1K"
        }
      },
      contents: {
        parts: [
          { text: systemPrompt },
          ...styleParts,
          ...faceParts,
          ...outfitParts,
          baseImagePart,
        ]
      }
    });

    if (response.candidates && response.candidates.length > 0) {
      const parts = response.candidates[0].content.parts;
      if (parts) {
        for (const part of parts) {
          if (part.inlineData && part.inlineData.data) {
            return `data:image/png;base64,${part.inlineData.data}`;
          }
        }
      }
    }
    throw new Error("No image generated.");
  } catch (error: any) {
    console.error("Gemini Generation Error:", error);
    throw new Error(error.message || "Failed to generate manga art.");
  }
};

export const generateClayModel = async (inputs: ModelInputs): Promise<string> => {
  const ai = getGeminiClient();
  const { imageBase64, userPrompt, physical, characters, styleImages, styleFeatures } = inputs;

  const sketchPart = toInlinePart(imageBase64);
  const styleParts = (styleImages || []).slice(0, 3).map(toInlinePart);

  const FACE_PER_CHAR = 2;
  const OUTFIT_PER_CHAR = 2;

  const COLORS_KO: Record<string, string> = {
    red: '빨간색', blue: '파란색', green: '초록색', amber: '노란색'
  };

  // Per-character reference parts: interleave text labels with image parts
  // so the model gets a strong "which image belongs to which character" signal.
  const characterRefParts: any[] = [];
  (characters || []).forEach((c) => {
    const faces = (c.faceImages || []).slice(0, FACE_PER_CHAR);
    const outfits = (c.outfitImages || []).slice(0, OUTFIT_PER_CHAR);
    if (faces.length === 0 && outfits.length === 0) return;

    const colorTag = c.color
      ? ` — marker: ${c.color.toUpperCase()} border (${COLORS_KO[c.color] || c.color} 테두리/폐곡선)`
      : '';
    characterRefParts.push({ text: `\n--- Character "${c.name}"${colorTag} ---` });

    if (faces.length > 0) {
      characterRefParts.push({
        text: `Face reference${faces.length > 1 ? 's' : ''} for "${c.name}" (translate identity into 3D — do not copy the 2D medium):`
      });
      faces.forEach(img => characterRefParts.push(toInlinePart(img)));
    }
    if (outfits.length > 0) {
      characterRefParts.push({
        text: `Outfit reference${outfits.length > 1 ? 's' : ''} for "${c.name}" (translate garment design into 3D — do not copy the 2D medium):`
      });
      outfits.forEach(img => characterRefParts.push(toInlinePart(img)));
    }
  });

  // Text-side mapping guide
  const mappingGuide = (characters || []).map(c => {
    const hasFace = ((c.faceImages || []).length) > 0;
    const hasOutfit = ((c.outfitImages || []).length) > 0;
    const refSummary = `${hasFace ? 'face-ref ✓' : 'face-ref ✗'}, ${hasOutfit ? 'outfit-ref ✓' : 'outfit-ref ✗'}`;
    const colorTag = c.color
      ? `${c.color.toUpperCase()} border (${COLORS_KO[c.color] || c.color} 테두리)`
      : '(no color marker)';
      
    let physText = [];
    if (c.height) physText.push(`Height: ${c.height}`);
    if (c.weight) physText.push(`Weight: ${c.weight}`);
    if (c.bodyType) physText.push(`Physique: ${c.bodyType}`);
    const physStr = physText.length > 0 ? ` | Physical: ${physText.join(', ')}` : '';
      
    return `- "${c.name}" — ${colorTag} — refs: ${refSummary}. Face text: ${c.facePrompt || '(none)'}. Outfit text: ${c.outfitPrompt || '(none)'}.${physStr}`;
  }).join('\n');

  const hasAnyCharacter = (characters || []).length > 0;
  const hasStyle = (styleParts.length > 0) || ((styleFeatures || '').trim().length > 0);

  // Build INPUT STRUCTURE description dynamically
  const inputStructureLines: string[] = [];
  let si = 1;
  if (hasStyle && styleParts.length > 0) {
    inputStructureLines.push(`  ${si++}. Character STYLE/VIBE reference images.`);
  }
  if (characterRefParts.length > 0) {
    inputStructureLines.push(`  ${si++}. Per-character FACE and OUTFIT references, grouped under labeled text headers.`);
  }
  inputStructureLines.push(`  ${si++}. STORYBOARD / SKETCH — the final input image, ground truth for framing/pose/composition (character placement marked via colored borders).`);

  // Build priorities — STORYBOARD always 1, then CHARACTER (if any), then STYLE (if any), then 3D OUTPUT last.
  const priorityLines: string[] = [];
  let p = 1;

  priorityLines.push(`${p++}. STORYBOARD GEOMETRY LOCK (HIGHEST PRIORITY) — the final input image is the ground truth for framing.
   You MUST replicate, not reinterpret. If any other rule conflicts with this, this rule wins.
   a. ASPECT RATIO & CROP: Output canvas matches the storyboard's frame exactly.
      The edges of the storyboard ARE the edges of the output.
   b. SHOT SIZE: If the storyboard shows a close-up (face/upper body only), the output
      is a close-up. If it shows a wide shot, the output is a wide shot.
      NEVER expand the framing to show more of the body than the storyboard shows.
      NEVER zoom in or out from what the storyboard depicts.
   c. CAMERA ANGLE: Eye-level / high-angle / low-angle / Dutch — match it precisely.
   d. COMPOSITION: Subject placement within the frame is preserved.
   e. POSE & MOTION: Body axis, limb angles, weight distribution, motion lines,
      and silhouette dynamics are preserved. Do not "fix" or "neutralize" an exaggerated pose.
   f. SILHOUETTE / FORM: The overall shape of each subject within the frame matches
      the storyboard's silhouette.`);

  if (hasAnyCharacter) {
    priorityLines.push(`${p++}. CHARACTER IDENTITY (per-character) — each character must read as a faithful translation of its OWN references.
   - Each character is marked in the storyboard by a colored border (mapping marker).
   - Use ONLY the reference images explicitly labeled under that character — DO NOT mix references across characters.
   - Preserve: hair shape/length/color, facial structure, key identifying features, outfit silhouette, layering, color palette, overall vibe.
   - Reference images may be 2D drawings, anime stills, or photographs. Translate the IDENTITY into 3D form; do NOT replicate their 2D medium.`);
  }

  if (hasStyle) {
    priorityLines.push(`${p++}. STYLE / VIBE — apply the appearance/vibe cue from the STYLE references.
   - This is a vibe/appearance cue ONLY (eye stylization, character proportions, atmosphere).
   - This is NOT the output medium. The output medium is 3D regardless of the style references' medium.`);
  }

  priorityLines.push(`${p++}. OUTPUT MEDIUM — high-end 3D CG render.
   - Aesthetic target: premium digital 3D illustration / high-end stylized anime 3D, like a polished animated feature still.
   - Fully shaded, volumetric, with depth, lighting, and material rendering. Volumetric hair, structured garments with thickness and folds, three-dimensional facial geometry, physically plausible lighting and cast shadows.
   - NO flat shading, NO cel-shading look, NO line art, NO sketch, NO 2D drawing.
   - DO NOT add a plastic figure stand, display base, or platform.`);

  const characterSection = hasAnyCharacter
    ? `\nCHARACTER MAPPING GUIDE:\n${mappingGuide}\n`
    : '';

  const styleAddon = (hasStyle && (styleFeatures || '').trim().length > 0)
    ? ` Additional character vibe/appearance notes: ${styleFeatures}.`
    : '';

  let physicalPrompt = "";
  if (physical) {
    const windLabels = ["none", "light", "moderate", "strong", "stormy", "hurricane"];
    const strength = windLabels[physical.windStrength] || "none";
    physicalPrompt = `PHYSICAL FORCES:
    - Wind: ${strength} strength from the ${physical.windDirection}.
    - Gravity: ${physical.gravityEnabled ? "Active, naturally affecting drapes and hair" : "Neutral"}.
    - EFFECT: Hair, clothing, and thin elements should flow accordingly.`;
  }

  const systemPrompt = `
You are generating a single output image.

INPUT STRUCTURE (in order):
${inputStructureLines.join('\n')}

PRIORITY ORDER (ABSOLUTE — top is most important; lower-priority rules NEVER override higher-priority ones):

${priorityLines.join('\n\n')}
${characterSection}
WHAT TO IGNORE FROM THE STORYBOARD (and ONLY these):
- The color borders themselves (mapping markers, not visual content).
- Generic placeholder faces and clothing drawn on the figures.
- Any numbers, labels, or annotation text.
EVERYTHING ELSE in the storyboard — frame edges, pose, scale within frame, angle, silhouette — is BINDING.

STYLE: High-end 3D anime/stylized aesthetic.${styleAddon}

${physicalPrompt}

User Instruction: "${userPrompt ? userPrompt : "Render this storyboard into a 3D scene with the specified characters."}"
`;

  try {
    const aspectRatio = await getAspectRatio(imageBase64);

    const styleSection = (hasStyle && styleParts.length > 0)
      ? [
          { text: '\n--- Character STYLE/VIBE references (vibe/appearance cue — do not copy the 2D medium) ---' },
          ...styleParts
        ]
      : [];

    const response = await ai.models.generateContent({
      model: 'gemini-3.1-flash-image-preview',
      config: {
        imageConfig: {
          aspectRatio: aspectRatio,
          imageSize: "1K"
        }
      },
      contents: {
        parts: [
          { text: systemPrompt },
          ...styleSection,
          ...characterRefParts,
          { text: '\n--- STORYBOARD / SKETCH (final input — defines framing, pose, character placement) ---' },
          sketchPart,
        ]
      }
    });

    if (response.candidates && response.candidates.length > 0) {
      const parts = response.candidates[0].content.parts;
      if (parts) {
        for (const part of parts) {
          if (part.inlineData && part.inlineData.data) {
            return `data:image/png;base64,${part.inlineData.data}`;
          }
        }
      }
    }
    throw new Error("No image generated.");
  } catch (error: any) {
    console.error("Gemini Generation Error:", error);
    throw new Error(error.message || "Failed to generate image.");
  }
};
