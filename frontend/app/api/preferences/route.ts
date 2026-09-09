import { assertLocalRequest, readJson } from "@/lib/local-request";
import { isLanguageCode, languageInfo } from "@/lib/languages";
import { loadWorkspace, mutateWorkspace } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    assertLocalRequest(request);
    const data = await loadWorkspace();
    return Response.json(
      { language: languageInfo(data.preferences?.language).code },
      {
        headers: { "Cache-Control": "no-store" },
      },
    );
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    assertLocalRequest(request);
    const body = await readJson(request);
    if (!isLanguageCode(body.language))
      throw new Error("Choose a supported language.");
    const language = body.language;
    await mutateWorkspace((data) => {
      data.preferences = { ...data.preferences, language };
    });
    return Response.json({ language });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
