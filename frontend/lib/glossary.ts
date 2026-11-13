/**
 * Plain-English glossary for every technical term in Distill.
 * Rule: One clear sentence. Zero buzzwords.
 */
export const GLOSSARY: Record<string, string> = {
  governed: "An official company storage location with managed backup and retention rules, treated as a trusted source of truth.",
  OneDrive: "Microsoft personal cloud storage for an individual employee, not managed by company retention rules.",
  SharePoint: "Microsoft team collaboration portal where official company documents and presentations are stored.",
  "Ericsson Play": "Ericsson's internal corporate video platform for sharing official recorded presentations and webinars.",
  OCR: "Optical Character Recognition: software that reads the printed letters and words visible on a screen or slide image.",
  pHash: "Perceptual hashing: a fingerprint algorithm that compares visual slide images even if slightly resized or compressed.",
  "SHA-256": "A cryptographic fingerprint that uniquely identifies a file by its exact bytes down to a single bit.",
  embedding: "A numerical signature that allows searching for sentences based on their meaning rather than exact keywords.",
  diarization: "Speaker detection: automatically identifying who spoke when throughout an audio recording.",
  quarantine: "A secure, reversible holding folder where duplicate files are moved instead of being deleted permanently.",
  "dry run": "A preview mode that checks what would happen without making any actual changes to any files.",
  "RapidOCR": "A lightweight, offline program that reads words visible on slide images using the laptop CPU.",
  "Whisper": "An offline speech recognition model from OpenAI that transcribes spoken audio into timestamped text.",
  "WebP": "A modern web image format that preserves slide graphics at a fraction of PNG or JPEG file size.",
  "Opus": "An efficient audio format optimized for human speech, preserving clear voice recordings at just 16 kbps.",
  "Level 1": "Level 1 Original: the untouched raw recording or document file, exactly as uploaded.",
  "Level 2": "Level 2 Smaller video: a playable video re-encoded at 5 frames per second for slide presentations.",
  "Level 3": "Level 3 Audio + slides + text: no video bitstream; preserves clear speech audio, slide pictures, and transcript.",
  "Level 4": "Level 4 Slides + text: no audio; keeps slide pictures, word-for-word transcript, and speaker names.",
  "Level 5": "Level 5 Text + links: slides that already exist in an official deck are linked, keeping only unique slides as pictures.",
};

export function getExplanation(term: string): string {
  if (GLOSSARY[term]) return GLOSSARY[term];
  const lower = term.toLowerCase();
  for (const [k, v] of Object.entries(GLOSSARY)) {
    if (k.toLowerCase() === lower) return v;
  }
  return "An enterprise file storage concept explained in plain language.";
}
