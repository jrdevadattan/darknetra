import { execFile } from "node:child_process";

const unreadable = (message) =>
  Object.assign(new Error(message), { code: "METADATA_UNREADABLE" });
const clean = (value, limit = 1200) =>
  String(value)
    .replace(/[\x00-\x1f\x7f]/g, " ")
    .slice(0, limit);
const captureTag =
  /:(?:DateTimeOriginal|SubSecDateTimeOriginal|DateCreated|CreateDate|CreationTime)$/i;
const gpsTag = /:(?:GPSLatitude|GPSLongitude|GPSPosition)$/i;

// Read the original bytes through stdin: no temporary image, upload filesystem
// dates, shell interpolation, automatic Perl config or metadata writes.
export function exiftoolBytes(bytes) {
  return new Promise((resolve, reject) => {
    const child = execFile(
      "exiftool",
      ["-config", "", "-j", "-G1", "-s", "-a", "--", "-"],
      {
        shell: false,
        windowsHide: true,
        timeout: 20000,
        maxBuffer: 512 * 1024,
      },
      (error, stdout) => {
        if (error)
          return reject(
            error.code === "ENOENT"
              ? Object.assign(
                  new Error("ExifTool is not installed in this runtime."),
                  { code: "TOOL_UNAVAILABLE" },
                )
              : unreadable(
                  "ExifTool could not read this file within its limits. Metadata remains unverified; try the original file or a supported format.",
                ),
          );
        resolve(stdout);
      },
    );
    // A failed/early-exiting child may close stdin before all bytes are sent.
    child.stdin.on("error", () => {});
    child.stdin.end(bytes);
  });
}

export function summarizeMetadata(records) {
  if (
    !Array.isArray(records) ||
    records.length !== 1 ||
    !records[0] ||
    typeof records[0] !== "object"
  )
    throw unreadable("ExifTool returned unreadable metadata.");
  const entries = Object.entries(records[0]);
  if (entries.some(([tag]) => /(?:^|:)Error$/i.test(tag)))
    throw unreadable(
      "ExifTool reported an unreadable file. Metadata remains unverified.",
    );
  const warnings = entries
    .filter(([tag]) => /(?:^|:)Warning$/i.test(tag))
    .map(([, value]) => clean(value, 300));
  const all = entries.filter(
    ([tag]) => tag !== "SourceFile" && !/^(?:System|ExifTool):/.test(tag),
  );
  if (!all.length)
    throw unreadable("No readable metadata result was returned.");
  const priority = (tag) =>
    captureTag.test(tag) ||
    gpsTag.test(tag) ||
    /:(?:Make|Model|Software|OffsetTime.*|Description|Title|Author|Creator|Artist)$/i.test(
      tag,
    )
      ? 0
      : 1;
  all.sort(([a], [b]) => priority(a) - priority(b));
  let truncated = all.length > 128;
  const fields = all.slice(0, 128).map(([tag, raw]) => {
    const value = typeof raw === "object" ? JSON.stringify(raw) : String(raw);
    if (value.length > 1200) truncated = true;
    return { tag: clean(tag, 160), value: clean(value) };
  });
  const captureTime = all.some(([tag]) => captureTag.test(tag))
    ? "present"
    : "not_found";
  const gps = all.some(([tag]) => gpsTag.test(tag)) ? "present" : "not_found";
  const notes = [
    captureTime === "present"
      ? "Embedded time tags found; their meaning and timezone need review."
      : "No capture-time tags found in this file.",
    gps === "present"
      ? "Embedded GPS tags found; these are unverified location claims."
      : "No GPS tags found in this file.",
    "Metadata is editable and does not establish identity, location or when the depicted event occurred. Filesystem/upload times are excluded.",
    ...warnings.map((warning) => `Extractor warning: ${warning}`),
  ];
  let text = [
    "Metadata checked.",
    ...notes,
    ...fields.map(({ tag, value }) => `${tag}: ${value}`),
  ].join("\n");
  if (text.length > 15000) {
    truncated = true;
    text = text.slice(0, 15000);
  }
  if (truncated)
    text +=
      "\nMetadata display truncated; some tags or long values are omitted.";
  return {
    analysis: "metadata",
    metadata: { captureTime, gps, warnings, truncated, fields },
    result: [Object.fromEntries(fields.map(({ tag, value }) => [tag, value]))],
    text,
  };
}

export async function readMetadata(bytes, reader = exiftoolBytes) {
  if (
    !Buffer.isBuffer(bytes) ||
    !bytes.length ||
    bytes.length > 32 * 1024 * 1024
  )
    throw Object.assign(
      new Error("Supply original file bytes, no larger than 32 MiB."),
      { code: "VALIDATION" },
    );
  const output = await reader(bytes);
  let records;
  try {
    records = JSON.parse(output);
  } catch {
    throw unreadable("ExifTool returned unreadable metadata.");
  }
  return summarizeMetadata(records);
}
