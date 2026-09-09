// SYNTHETIC sandbox regression check; only tries its own new marker file.
const fs = require("node:fs");
const path = require("node:path");
const marker = path.join(process.cwd(), "SYNTHETIC-readonly-marker");
try {
  fs.writeFileSync(marker, "SYNTHETIC", { flag: "wx" });
  console.log("FAIL: filesystem write was allowed");
  process.exitCode = 1;
} catch (error) {
  if (!["EACCES", "EPERM", "EROFS"].includes(error.code)) throw error;
  console.log("PASS: filesystem write denied by sandbox");
}
