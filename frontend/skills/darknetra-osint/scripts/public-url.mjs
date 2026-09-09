import net from "node:net";
import ipaddr from "ipaddr.js";
const fail = (code, message) => Object.assign(new Error(message), { code });

export function isPublicAddress(address) {
  try {
    return ipaddr.process(address).range() === "unicast";
  } catch {
    return false;
  }
}

export function publicUrl(value) {
  if (
    typeof value !== "string" ||
    value.length > 4096 ||
    /[\s\\\x00-\x1f\x7f]/.test(value)
  )
    throw fail("VALIDATION", "Invalid public URL.");
  let url;
  try {
    url = new URL(value);
  } catch {
    throw fail("VALIDATION", "An absolute HTTP(S) URL is required.");
  }
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.port
  )
    throw fail(
      "VALIDATION",
      "Use HTTP(S), standard ports and no URL credentials.",
    );
  const host = url.hostname.replace(/^\[|\]$/g, "");
  if (host.endsWith(".onion")) {
    if (!/^[a-z2-7]{56}\.onion$/.test(host))
      throw fail("VALIDATION", "A v3 onion address is required.");
  } else if (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    !host.includes(".") ||
    (net.isIP(host) && !isPublicAddress(host))
  ) {
    throw fail("POLICY_DENIED", "Only public network sources are supported.");
  }
  url.hash = "";
  return url;
}
