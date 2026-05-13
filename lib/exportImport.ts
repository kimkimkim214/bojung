import JSZip from 'jszip';
import { saveAs } from 'file-saver';
import { Character, GenerationHistoryItem, OutfitSet } from '../types';

function dataURItoBlob(dataURI: string): Blob {
  const byteString = atob(dataURI.split(',')[1]);
  const mimeString = dataURI.split(',')[0].split(':')[1].split(';')[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  return new Blob([ab], { type: mimeString });
}

function blobToDataURI(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target?.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// 파일명 확장자로 image MIME 타입 추론 (JSZip blob은 type이 비어있어서 필요)
function mimeFromFilename(name: string): string {
  const ext = name.toLowerCase().split('.').pop() || '';
  if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg';
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  if (ext === 'gif') return 'image/gif';
  return 'image/png';
}

// JSZip blob (type 비어있음) → 올바른 image/* MIME 가진 dataURI로 변환
async function zipImageToDataURI(zip: JSZip, path: string): Promise<string> {
  const entry = zip.file(path);
  if (!entry) throw new Error(`Missing file in zip: ${path}`);
  const rawBlob = await entry.async('blob');
  const filename = path.split('/').pop() || path;
  const typedBlob = new Blob([rawBlob], { type: mimeFromFilename(filename) });
  return blobToDataURI(typedBlob);
}

function extractExtensionFromMime(mime: string): string {
  if (mime === 'image/jpeg') return 'jpg';
  if (mime === 'image/png') return 'png';
  if (mime === 'image/webp') return 'webp';
  return 'png';
}

function extractExtensionFromDataURI(dataURI: string): string {
  const mimeStr = dataURI.split(',')[0].split(':')[1].split(';')[0];
  return extractExtensionFromMime(mimeStr);
}

export const exportCharacter = async (character: Character, history: GenerationHistoryItem[]) => {
  const zip = new JSZip();

  // 1. profile.json
  const profile = {
    id: character.id,
    name: character.name,
    color: character.color,
    height: character.height,
    weight: character.weight,
    bodyType: character.bodyType,
    facePrompt: character.facePrompt,
    activeOutfitSetId: character.activeOutfitSetId,
    outfitSetsMeta: character.outfitSets.map(o => ({
      id: o.id,
      name: o.name,
      prompt: o.prompt
    }))
  };
  zip.file('profile.json', JSON.stringify(profile, null, 2));

  // 2. face/
  const faceFolder = zip.folder('face');
  if (faceFolder) {
    character.faceImages.forEach((img, idx) => {
      const ext = extractExtensionFromDataURI(img);
      faceFolder.file(`ref_${idx + 1}.${ext}`, dataURItoBlob(img));
    });
  }

  // 3. outfits
  character.outfitSets.forEach((outfit) => {
    const safeName = outfit.name.replace(/[^a-zA-Z0-9가-힣_]/g, '_');
    const outfitFolder = zip.folder(`outfit_${safeName}_${outfit.id}`);
    if (outfitFolder) {
      outfit.images.forEach((img, idx) => {
        const ext = extractExtensionFromDataURI(img);
        outfitFolder.file(`ref_${idx + 1}.${ext}`, dataURItoBlob(img));
      });
    }
  });

  // 4. accumulated outputs
  const charHistory = history.filter(h => h.charactersInfo?.some(ci => ci.name === character.name));
  const accFolder = zip.folder('accumulated');
  if (accFolder) {
    charHistory.forEach((item, idx) => {
      if (item.generatedImage) {
        const ext = extractExtensionFromDataURI(item.generatedImage);
        const prefix = item.type === 'manga' ? 'manga' : 'figurine';
        accFolder.file(`${prefix}_${String(idx + 1).padStart(3, '0')}.${ext}`, dataURItoBlob(item.generatedImage));
      }
    });
  }

  const content = await zip.generateAsync({ type: 'blob' });
  const safeCharName = character.name.replace(/[^a-zA-Z0-9가-힣_]/g, '_') || 'Unnamed';
  saveAs(content, `character_${safeCharName}.zip`);
};

export const exportProject = async (characters: Character[], history: GenerationHistoryItem[]) => {
  const zip = new JSZip();

  const projectMeta = {
    version: 1,
    exportedAt: new Date().toISOString()
  };
  zip.file('project.json', JSON.stringify(projectMeta, null, 2));

  for (const char of characters) {
    const safeCharName = char.name.replace(/[^a-zA-Z0-9가-힣_]/g, '_') || char.id;
    const charFolder = zip.folder(`character_${safeCharName}`);
    if (!charFolder) continue;

    const profile = {
      id: char.id,
      name: char.name,
      color: char.color,
      height: char.height,
      weight: char.weight,
      bodyType: char.bodyType,
      facePrompt: char.facePrompt,
      activeOutfitSetId: char.activeOutfitSetId,
      outfitSetsMeta: char.outfitSets.map(o => ({
        id: o.id,
        name: o.name,
        prompt: o.prompt
      }))
    };
    charFolder.file('profile.json', JSON.stringify(profile, null, 2));

    const faceFolder = charFolder.folder('face');
    if (faceFolder) {
      char.faceImages.forEach((img, idx) => {
        const ext = extractExtensionFromDataURI(img);
        faceFolder.file(`ref_${idx + 1}.${ext}`, dataURItoBlob(img));
      });
    }

    char.outfitSets.forEach((outfit) => {
      const safeOutfitName = outfit.name.replace(/[^a-zA-Z0-9가-힣_]/g, '_');
      const outfitFolder = charFolder.folder(`outfit_${safeOutfitName}_${outfit.id}`);
      if (outfitFolder) {
        outfit.images.forEach((img, idx) => {
          const ext = extractExtensionFromDataURI(img);
          outfitFolder.file(`ref_${idx + 1}.${ext}`, dataURItoBlob(img));
        });
      }
    });

    const charHistory = history.filter(h => h.charactersInfo?.some(ci => ci.name === char.name));
    const accFolder = charFolder.folder('accumulated');
    if (accFolder) {
      charHistory.forEach((item, idx) => {
        if (item.generatedImage) {
          const ext = extractExtensionFromDataURI(item.generatedImage);
          const prefix = item.type === 'manga' ? 'manga' : 'figurine';
          accFolder.file(`${prefix}_${String(idx + 1).padStart(3, '0')}.${ext}`, dataURItoBlob(item.generatedImage));
        }
      });
    }
  }

  // Also backup full history raw data if needed
  zip.file('history_raw.json', JSON.stringify(history, null, 2));

  const content = await zip.generateAsync({ type: 'blob' });
  saveAs(content, `claymorph_project_${new Date().getTime()}.zip`);
};

export const importZip = async (file: File): Promise<{ characters: Character[], history: GenerationHistoryItem[] } | null> => {
  const zip = new JSZip();
  await zip.loadAsync(file);

  const importedCharacters: Character[] = [];
  let importedHistory: GenerationHistoryItem[] = [];

  let projectFile = zip.file('project.json');
  let projectBasePath = '';
  if (!projectFile) {
    const pFiles = zip.file(/project\.json$/).filter(f => !f.name.includes('__MACOSX'));
    if (pFiles.length > 0) {
        projectFile = pFiles[0];
        projectBasePath = projectFile.name.substring(0, projectFile.name.lastIndexOf('project.json'));
    }
  }

  const isProject = projectFile !== null;

  if (!isProject) {
    // Single character import
    let profileFile = zip.file('profile.json');
    let basePath = '';
    if (!profileFile) {
       const pFiles = zip.file(/profile\.json$/).filter(f => !f.name.includes('__MACOSX'));
       if (pFiles.length > 0) {
           profileFile = pFiles[0];
           basePath = profileFile.name.substring(0, profileFile.name.lastIndexOf('profile.json'));
       }
    }

    if (!profileFile) throw new Error("Invalid character archive: missing profile.json");
    
    const profileText = await profileFile.async('string');
    const profile = JSON.parse(profileText);

    const character: Character = {
      id: profile.id || Date.now().toString(),
      name: profile.name || '',
      color: profile.color || 'red',
      height: profile.height,
      weight: profile.weight,
      bodyType: profile.bodyType,
      facePrompt: profile.facePrompt || '',
      faceImages: [],
      outfitSets: [],
      activeOutfitSetId: profile.activeOutfitSetId || ''
    };

    // Load face images
    const faceImages: { name: string, dataURI: string }[] = [];
    zip.folder(`${basePath}face`)?.forEach((relativePath, file) => {
      if (!file.dir) faceImages.push({ name: relativePath, dataURI: '' });
    });
    for (const f of faceImages) {
      f.dataURI = await zipImageToDataURI(zip, `${basePath}face/${f.name}`);
    }
    character.faceImages = faceImages.map(f => f.dataURI);

    // Load outfits
    if (profile.outfitSetsMeta) {
      for (const meta of profile.outfitSetsMeta) {
        const safeOutfitName = meta.name.replace(/[^a-zA-Z0-9가-힣_]/g, '_');
        const outfitPath = `${basePath}outfit_${safeOutfitName}_${meta.id}`;
        
        const outfitImages: { name: string, dataURI: string }[] = [];
        zip.folder(outfitPath)?.forEach((relativePath, file) => {
          if (!file.dir) outfitImages.push({ name: relativePath, dataURI: '' });
        });

        const images = [];
        for (const f of outfitImages) {
           images.push(await zipImageToDataURI(zip, `${outfitPath}/${f.name}`));
        }

        character.outfitSets.push({
          id: meta.id,
          name: meta.name,
          prompt: meta.prompt,
          images: images
        });
      }
    }
    importedCharacters.push(character);
  } else {
    // Read raw history if exists
    const historyFile = zip.file(projectBasePath + 'history_raw.json');
    if (historyFile) {
        try {
            importedHistory = JSON.parse(await historyFile.async('string'));
        } catch(e) {}
    }

    // Project import
    const rootFolders = new Set<string>();
    zip.forEach((relativePath) => {
      const pathToCheck = projectBasePath && relativePath.startsWith(projectBasePath)
        ? relativePath.substring(projectBasePath.length) 
        : relativePath;
      const parts = pathToCheck.split('/');
      if (parts[0].startsWith('character_')) {
        rootFolders.add(projectBasePath + parts[0]);
      }
    });

    for (const charFolderName of Array.from(rootFolders)) {
      const profileFile = zip.file(`${charFolderName}/profile.json`);
      if (!profileFile) continue;

      const profileText = await profileFile.async('string');
      const profile = JSON.parse(profileText);

      const character: Character = {
        id: profile.id || Date.now().toString(),
        name: profile.name || '',
        color: profile.color || 'red',
        height: profile.height,
        weight: profile.weight,
        bodyType: profile.bodyType,
        facePrompt: profile.facePrompt || '',
        faceImages: [],
        outfitSets: [],
        activeOutfitSetId: profile.activeOutfitSetId || ''
      };

      // Load face images
      const faceImages: { name: string, dataURI: string }[] = [];
      zip.folder(`${charFolderName}/face`)?.forEach((relativePath, file) => {
        if (!file.dir) faceImages.push({ name: relativePath, dataURI: '' });
      });
      for (const f of faceImages) {
        f.dataURI = await zipImageToDataURI(zip, `${charFolderName}/face/${f.name}`);
      }
      character.faceImages = faceImages.map(f => f.dataURI);

      // Load outfits
      if (profile.outfitSetsMeta) {
        for (const meta of profile.outfitSetsMeta) {
          const safeOutfitName = meta.name.replace(/[^a-zA-Z0-9가-힣_]/g, '_');
          const outfitPath = `${charFolderName}/outfit_${safeOutfitName}_${meta.id}`;
          
          const outfitImages: { name: string, dataURI: string }[] = [];
          zip.folder(outfitPath)?.forEach((relativePath, file) => {
            if (!file.dir) outfitImages.push({ name: relativePath, dataURI: '' });
          });
  
          const images = [];
          for (const f of outfitImages) {
             images.push(await zipImageToDataURI(zip, `${outfitPath}/${f.name}`));
          }
  
          character.outfitSets.push({
            id: meta.id,
            name: meta.name,
            prompt: meta.prompt,
            images: images
          });
        }
      }
      importedCharacters.push(character);
    }
  }

  return { characters: importedCharacters, history: importedHistory };
};
