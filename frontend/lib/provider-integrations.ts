import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

export type ProviderIntegration = {
  id: string;
  name: string;
  command: string;
  capability: string;
  setupUrl: string;
  state:
    "credentials_required" | "configured_unverified" | "configuration_error";
  message?: string;
};

export async function providerIntegrations(): Promise<{
  providers: ProviderIntegration[];
  note: string;
}> {
  try {
    const { stdout } = await promisify(execFile)(
      process.execPath,
      [
        path.join(process.cwd(), "skills/darknetra-osint/scripts/osint.mjs"),
        "integrations",
      ],
      { timeout: 8000, maxBuffer: 32000, windowsHide: true },
    );
    const result = JSON.parse(stdout);
    if (result.ok !== true || !Array.isArray(result.data?.providers))
      throw new Error();
    return result.data;
  } catch {
    throw new Error("Could not read intelligence tool configuration.");
  }
}
