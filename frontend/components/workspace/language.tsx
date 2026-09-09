"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Check, Languages, LoaderCircle } from "lucide-react";
import {
  isLanguageCode,
  languageInfo,
  languages,
  type LanguageCode,
} from "@/lib/languages";
import { translate } from "@/lib/translations";

const LanguageContext = createContext({
  language: "en" as LanguageCode,
  t: (text: string) => text,
  setLanguage: async (_language: LanguageCode) => {},
  saving: false,
  ready: false,
  error: "",
});
export const useLanguage = () => useContext(LanguageContext);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, updateLanguage] = useState<LanguageCode>("en");
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const revision = useRef(0);
  useEffect(() => {
    let active = true;
    async function refresh() {
      const current = revision.current;
      try {
        const response = await fetch("/api/preferences", { cache: "no-store" });
        if (!response.ok) throw new Error("Could not load language settings.");
        const value = await response.json();
        if (
          active &&
          !pending.current &&
          current === revision.current &&
          isLanguageCode(value.language)
        ) {
          updateLanguage(value.language);
          setError("");
        }
      } catch {
        if (active) setError("Could not load language settings. Try again.");
      } finally {
        if (active) setReady(true);
      }
    }
    void refresh();
    window.addEventListener("focus", refresh);
    return () => {
      active = false;
      window.removeEventListener("focus", refresh);
    };
  }, []);
  useEffect(() => {
    const info = languageInfo(language);
    document.documentElement.lang = language;
    document.documentElement.dir = "dir" in info ? info.dir : "ltr";
  }, [language]);
  const setLanguage = useCallback(async (next: LanguageCode) => {
    if (pending.current || !isLanguageCode(next)) return;
    pending.current = true;
    revision.current++;
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: next }),
      });
      if (!response.ok)
        throw new Error("Could not save the language. Try again.");
      updateLanguage(next);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      pending.current = false;
      setSaving(false);
    }
  }, []);
  const value = useMemo(
    () => ({
      language,
      setLanguage,
      saving,
      ready,
      error,
      t: (text: string) => translate(language, text),
    }),
    [language, setLanguage, saving, ready, error],
  );
  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function LanguageSettings() {
  const { language, setLanguage, t, saving, ready, error } = useLanguage();
  return (
    <fieldset className="language-settings">
      <legend>
        <Languages size={17} /> {t("Language")}{" "}
        <small lang="en" dir="ltr">
          Language
        </small>
      </legend>
      <label className="sr-only" htmlFor="workspace-language">
        {t("Language")} / Language
      </label>
      <div className="language-select-row">
        <select
          id="workspace-language"
          value={language}
          disabled={saving || !ready}
          onChange={(event) =>
            void setLanguage(event.target.value as LanguageCode)
          }
          dir="ltr"
        >
          {languages.map((item) => (
            <option key={item.code} value={item.code} lang={item.code}>
              {item.name}
              {item.code === "en" ? "" : ` — ${item.native}`}
            </option>
          ))}
        </select>
        {saving ? (
          <LoaderCircle className="spin" size={17} />
        ) : (
          <Check size={17} aria-hidden="true" />
        )}
      </div>
      <p lang="en" dir="ltr">
        Interface labels and future assistant replies. English + all 22
        scheduled Indian languages. Original evidence is preserved.
      </p>
      <p lang="en" dir="ltr" className="muted">
        Some help text and technical messages remain in English.
      </p>
      <span className="sr-only" role="status">
        {saving ? t("Saving…") : ready && !error ? t("Language saved") : ""}
      </span>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}
