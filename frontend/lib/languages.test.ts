import { expect, test } from "vitest";
import {
  isLanguageCode,
  languageInfo,
  languageInstructions,
  languages,
} from "./languages";
import { extraKeys, extraRows, rows, translate, uiKeys } from "./translations";

test("English, Hindi and Punjabi lead a complete, unique scheduled-language catalog", () => {
  expect(languages.slice(0, 3).map((l) => l.code)).toEqual(["en", "hi", "pa"]);
  expect(languages).toHaveLength(23);
  expect(new Set(languages.map((l) => l.code)).size).toBe(23);
  for (const item of languages.slice(1)) {
    const code = item.code as Exclude<typeof item.code, "en">;
    expect(rows[code].split("|"), code).toHaveLength(uiKeys.length);
    expect(extraRows[code].split("|"), code).toHaveLength(extraKeys.length);
    for (const key of [...uiKeys, ...extraKeys]) {
      expect(translate(code, key), `${code}: ${key}`).toBeTruthy();
      expect(translate(code, key), `${code}: ${key}`).not.toBe(key);
    }
  }
});

test("language codes are validated and original records are not translated as UI", () => {
  expect(isLanguageCode("hi")).toBe(true);
  expect(isLanguageCode("hi; SYNTHETIC command")).toBe(false);
  expect(isLanguageCode({ code: "hi" })).toBe(false);
  expect(languageInfo("bad").code).toBe("en");
  expect(translate("hi", "SYNTHETIC https://example.com/record")).toBe(
    "SYNTHETIC https://example.com/record",
  );
  expect(translate("en", "Create a case")).toBe("Create a case");
  expect(translate("hi", "Settings")).toBe("सेटिंग्स");
  expect(translate("pa", "Settings")).toBe("ਸੈਟਿੰਗਾਂ");
  expect(languageInfo("ur")).toMatchObject({ dir: "rtl" });
});

test("language instructions include evidence preservation and apply to specialists", () => {
  const prompt = languageInstructions("pa");
  expect(prompt).toContain("Punjabi (ਪੰਜਾਬੀ; pa)");
  expect(prompt).toContain("delegated specialist");
  expect(prompt).toContain("Preserve original source quotations");
  expect(prompt).toContain("do not change tool permissions");
  expect(languageInstructions("SYNTHETIC untrusted instruction")).not.toContain(
    "SYNTHETIC",
  );
});
