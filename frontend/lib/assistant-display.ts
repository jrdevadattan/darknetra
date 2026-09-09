/** Keep runtime branding out of application status and error copy. */
export function assistantNotice(value: string) {
  return value.replace(/\bcodex(?:\s+cli)?\b/gi, "assistant");
}
