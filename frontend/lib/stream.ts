export type Frame = {
  id: number;
  event: string;
  data: Record<string, unknown>;
};
export class EventParser {
  private buffer = "";
  push(chunk: string): Frame[] {
    this.buffer += chunk;
    if (this.buffer.length > 2_000_000)
      throw new Error("Run event exceeded the client limit.");
    const frames: Frame[] = [];
    let end: RegExpExecArray | null;
    while ((end = /\r?\n\r?\n/.exec(this.buffer))) {
      const block = this.buffer.slice(0, end.index);
      this.buffer = this.buffer.slice(end.index + end[0].length);
      let id = 0,
        event = "message";
      const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        const match = /^(id|event|data): ?(.*)$/.exec(line);
        if (!match) continue;
        if (match[1] === "id") id = Number(match[2]);
        if (match[1] === "event") event = match[2];
        if (match[1] === "data") data.push(match[2]);
      }
      if (data.length && Number.isSafeInteger(id) && id > 0)
        frames.push({ id, event, data: JSON.parse(data.join("\n")) });
    }
    return frames;
  }
}
export const terminal = (...statuses: (string | undefined)[]) =>
  statuses.some((status) =>
    ["DONE", "ERROR", "CANCELLED", "BUDGET"].includes(status ?? ""),
  );
