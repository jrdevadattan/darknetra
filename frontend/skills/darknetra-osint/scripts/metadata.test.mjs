import { expect, test } from "vitest";
import { summarizeMetadata, readMetadata } from "./metadata.mjs";

test("metadata preserves embedded tags and separates them from filesystem dates", () => {
  const result = summarizeMetadata([
    {
      SourceFile: "/SYNTHETIC/private",
      "System:FileModifyDate": "2026:09:08 12:00:00",
      "ExifTool:ExifToolVersion": 12.57,
      "File:FileType": "JPEG",
      "EXIF:Make": "SYNTHETIC",
      "ExifIFD:DateTimeOriginal": "2020:01:02 03:04:05",
      "ExifIFD:OffsetTimeOriginal": "+05:30",
      "GPS:GPSLatitude": "0 deg 0' 0.00\" N",
      "GPS:GPSLongitude": "0 deg 0' 0.00\" E",
      "XMP-dc:Description": "SYNTHETIC fixture",
    },
  ]);
  expect(result.analysis).toBe("metadata");
  expect(result.text).toContain("2020:01:02 03:04:05");
  expect(result.text).toContain("+05:30");
  expect(result.text).toContain("GPSLatitude");
  expect(result.text).not.toContain("2026:09:08");
  expect(JSON.stringify(result)).not.toContain("/SYNTHETIC/private");
  expect(result.metadata.captureTime).toBe("present");
  expect(result.metadata.gps).toBe("present");
  expect(result.text).toContain("editable");
});

test("missing embedded tags are a completed check, not an extraction failure", () => {
  const result = summarizeMetadata([
    { "File:FileType": "PNG", "PNG:ImageWidth": 2, "PNG:ImageHeight": 3 },
  ]);
  expect(result.metadata.captureTime).toBe("not_found");
  expect(result.metadata.gps).toBe("not_found");
  expect(result.text).toContain("No capture-time tags found");
  expect(result.text).toContain("No GPS tags found");
  expect(result.text).toContain("PNG:ImageWidth: 2");
  expect(result.text).not.toContain("stripped");
});

test("malformed metadata and unreadable files cannot become successful checks", async () => {
  expect(() =>
    summarizeMetadata([{ "ExifTool:Error": "SYNTHETIC unreadable file" }]),
  ).toThrow("unreadable");
  expect(() => summarizeMetadata([])).toThrow();
  await expect(
    readMetadata(Buffer.from("SYNTHETIC"), async () => "invalid JSON"),
  ).rejects.toMatchObject({ code: "METADATA_UNREADABLE" });
  const warnings = summarizeMetadata([
    { "File:FileType": "PNG", "ExifTool:Warning": "SYNTHETIC incomplete tags" },
  ]);
  expect(warnings.metadata.warnings).toContain("SYNTHETIC incomplete tags");
  expect(warnings.text).toContain("incomplete tags");
});

test("metadata output bounds large embedded values and explicitly labels truncation", () => {
  const result = summarizeMetadata([
    { "File:FileType": "PNG", "PNG:Description": "SYNTHETIC ".repeat(10000) },
  ]);
  expect(result.metadata.truncated).toBe(true);
  expect(result.text.length).toBeLessThan(16000);
  expect(result.text).toContain("truncated");
});
