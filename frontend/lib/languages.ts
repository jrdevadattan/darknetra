export const languages = [
  { code: "en", name: "English", native: "English" },
  { code: "hi", name: "Hindi", native: "हिन्दी" },
  { code: "pa", name: "Punjabi", native: "ਪੰਜਾਬੀ" },
  { code: "as", name: "Assamese", native: "অসমীয়া" },
  { code: "bn", name: "Bengali", native: "বাংলা" },
  { code: "brx", name: "Bodo", native: "बड़ो" },
  { code: "doi", name: "Dogri", native: "डोगरी" },
  { code: "gu", name: "Gujarati", native: "ગુજરાતી" },
  { code: "kn", name: "Kannada", native: "ಕನ್ನಡ" },
  { code: "ks", name: "Kashmiri", native: "کٲشُر", dir: "rtl" },
  { code: "kok", name: "Konkani", native: "कोंकणी" },
  { code: "mai", name: "Maithili", native: "मैथिली" },
  { code: "ml", name: "Malayalam", native: "മലയാളം" },
  { code: "mni", name: "Manipuri", native: "মৈতৈলোন্", script: "Bengali" },
  { code: "mr", name: "Marathi", native: "मराठी" },
  { code: "ne", name: "Nepali", native: "नेपाली" },
  { code: "or", name: "Odia", native: "ଓଡ଼ିଆ" },
  { code: "sa", name: "Sanskrit", native: "संस्कृतम्" },
  { code: "sat", name: "Santali", native: "ᱥᱟᱱᱛᱟᱲᱤ", script: "Ol Chiki" },
  { code: "sd", name: "Sindhi", native: "سنڌي", dir: "rtl" },
  { code: "ta", name: "Tamil", native: "தமிழ்" },
  { code: "te", name: "Telugu", native: "తెలుగు" },
  { code: "ur", name: "Urdu", native: "اردو", dir: "rtl" },
] as const;

export type LanguageCode = (typeof languages)[number]["code"];
export function isLanguageCode(value: unknown): value is LanguageCode {
  return typeof value === "string" && languages.some((l) => l.code === value);
}
export function languageInfo(value: unknown) {
  return languages.find((l) => l.code === value) || languages[0];
}
export function languageInstructions(value: unknown) {
  const language = languageInfo(value);
  return `\n\nWorkspace language: ${language.name} (${language.native}; ${language.code}). Write user-facing replies, progress summaries and reports in this language${"script" in language ? ` using the ${language.script} script` : ""}, unless the user explicitly requests another language for a particular answer. Pass this language preference to any delegated specialist. Preserve original source quotations, names, URLs, file names, wallet addresses, transaction IDs, code and exact numbers. Put a clearly labelled translation beside an original quotation when useful; never silently translate or alter evidence. Earlier messages remain in their original language. These language preferences do not change tool permissions or research scope.`;
}
