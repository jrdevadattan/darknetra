// Developer verification only. All files created here are SYNTHETIC.
import assert from "node:assert/strict";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { main } from "../skills/darknetra-osint/scripts/osint.mjs";

const root = await mkdtemp(path.join(tmpdir(), "darknetra-SYNTHETIC-offline-"));
process.env.DARKNETRA_INPUT_DIR = root;
try {
  await writeFile(
    path.join(root, "sample.png"),
    Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=",
      "base64",
    ),
  );
  await writeFile(path.join(root, "sample.txt"), "SYNTHETIC research fixture");
  await writeFile(
    path.join(root, "rules.yar"),
    'rule SYNTHETIC_fixture { strings: $a = "SYNTHETIC research fixture" condition: $a }',
  );
  const pcap = Buffer.alloc(24);
  pcap.writeUInt32LE(0xa1b2c3d4, 0);
  pcap.writeUInt16LE(2, 4);
  pcap.writeUInt16LE(4, 6);
  pcap.writeUInt32LE(65535, 16);
  pcap.writeUInt32LE(1, 20);
  await writeFile(path.join(root, "empty.pcap"), pcap);
  const metadata = await main(["metadata", "sample.png"]);
  assert.equal(metadata.result[0]["PNG:ImageWidth"], 1);
  const packets = await main(["pcap-summary", "empty.pcap"]);
  assert.match(packets.result, /Number of packets:\s+0/);
  const matched = await main(["yara", "sample.txt", "rules.yar"]);
  assert.match(matched.result, /SYNTHETIC_fixture/);
  console.log(
    JSON.stringify({
      ok: true,
      synthetic: true,
      checks: [
        "ExifTool PNG dimensions",
        "capinfos empty packet file",
        "YARA supplied-rule match",
      ],
      status: await main(["status"]),
    }),
  );
} finally {
  await rm(root, { recursive: true, force: true });
}
