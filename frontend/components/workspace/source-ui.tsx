"use client";
import { createContext, useContext, useState, type ReactNode } from "react";
import {
  Archive,
  ArrowUpRight,
  Check,
  Copy,
  Download,
  File,
  FileArchive,
  FileImage,
  FileSearch,
  FileText,
  FolderSearch,
  Globe,
  History,
  Landmark,
  MessageCircle,
  Network,
  PackageSearch,
  Scale,
  Search,
  ShieldCheck,
  Table2,
  UsersRound,
  Wrench,
} from "lucide-react";
import { MessageResponse } from "@/components/ai-elements/message";
import { defaultRemarkPlugins } from "streamdown";
import { faviconData, sourceUrl } from "@/lib/run-activity";
import type { ChatAttachment, RunSource } from "@/lib/chat-types";

export function siteName(value?: string) {
  try {
    return new URL(value!).hostname.replace(/^www\./, "");
  } catch {
    return "Website";
  }
}
export function FileIcon({
  name = "",
  size = 17,
}: {
  name?: string;
  size?: number;
}) {
  const Icon = /\.(png|jpe?g|webp|gif|ico)$/i.test(name)
    ? FileImage
    : /\.(csv|xlsx?)$/i.test(name)
      ? Table2
      : /\.(zip|gz|7z)$/i.test(name)
        ? FileArchive
        : /\.(pcap|pcapng)$/i.test(name)
          ? Network
          : /\.(txt|md|pdf|docx?|json)$/i.test(name)
            ? FileText
            : File;
  return <Icon size={size} aria-hidden="true" />;
}
export function SiteIcon({
  url,
  favicon,
  size = 18,
}: {
  url?: string;
  favicon?: string;
  size?: number;
}) {
  const icon = faviconData(favicon);
  const [failed, setFailed] = useState<string>();
  return (
    <span
      className="site-icon"
      style={{ width: size + 12, height: size + 12 }}
      title={siteName(url)}
      aria-hidden="true"
    >
      {icon && failed !== icon ? (
        <img
          src={icon}
          alt=""
          width={size}
          height={size}
          onError={() => setFailed(icon)}
        />
      ) : (
        <Globe size={size} />
      )}
    </span>
  );
}
export function InvestigatorIcon({
  name,
  size = 18,
}: {
  name: string;
  size?: number;
}) {
  const Icon = /financial/i.test(name)
    ? Landmark
    : /postal|logistics/i.test(name)
      ? PackageSearch
      : /legal/i.test(name)
        ? Scale
        : /log review|log_review/i.test(name)
          ? Network
          : /file/i.test(name)
            ? FileSearch
            : /records/i.test(name)
              ? History
              : /research/i.test(name)
                ? Search
                : /liaison/i.test(name)
                  ? FolderSearch
                  : ShieldCheck;
  return <Icon size={size} aria-hidden="true" />;
}
export function ActionIcon({
  label,
  size = 15,
}: {
  label: string;
  size?: number;
}) {
  const Icon = /archive|history/i.test(label)
    ? Archive
    : /file|attached/i.test(label)
      ? FileSearch
      : /capture/i.test(label)
        ? Network
        : /source|published|website/i.test(label) && !/search/i.test(label)
          ? Globe
          : /search|index/i.test(label)
            ? Search
            : /tool|connectivity/i.test(label)
              ? Wrench
              : /progress|update/i.test(label)
                ? MessageCircle
                : /review|assign/i.test(label)
                  ? UsersRound
                  : Search;
  return <Icon size={size} aria-hidden="true" />;
}
export function CopyControl({
  value,
  label = "Copy link",
}: {
  value: string;
  label?: string;
}) {
  const [state, setState] = useState("");
  return (
    <button
      type="button"
      className="icon-button copy-control"
      aria-label={state || label}
      title={state || label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setState("Copied");
        } catch {
          setState("Copy failed");
        }
        setTimeout(() => setState(""), 2000);
      }}
    >
      {state === "Copied" ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}
export function attachmentLink(
  value: string | undefined,
  chatId?: string,
  files: ChatAttachment[] = [],
) {
  if (!value || !chatId) return;
  try {
    const name = decodeURIComponent(
      value.split(/[?#]/)[0].replace(/\\/g, "/").split("/").at(-1)!,
    );
    const file = files.find((f) => f.name === name);
    if (file)
      return {
        url: `/api/chat/${chatId}/files?name=${encodeURIComponent(file.name)}`,
        label: file.label,
      };
  } catch {
    /* Unknown paths are not links to the local filesystem. */
  }
}
const sourceStates: Record<string, string> = {
  retrieved: "Retrieved",
  analysed: "Examined",
  supplied: "Uploaded",
  listed: "Unverified reference",
  referenced: "Referenced",
  unavailable: "Unavailable",
};
export function SourceCard({
  source,
  onInspect,
  chatId,
  files = [],
}: {
  source: RunSource;
  onInspect?: (id: string) => void;
  chatId?: string;
  files?: ChatAttachment[];
}) {
  const url = sourceUrl(source.url);
  const file = attachmentLink(source.file, chatId, files);
  const href = url || file?.url;
  const title = file?.label || source.title;
  return (
    <div className="source-tile">
      <button
        type="button"
        className="source-select"
        title={`Inspect ${title}`}
        onClick={() => onInspect?.(source.id)}
        disabled={!onInspect}
      >
        {url ? (
          <SiteIcon url={url} favicon={source.favicon} />
        ) : (
          <span className="source-file-icon">
            <FileIcon name={title} />
          </span>
        )}
        <span className="source-tile-text">
          <strong>{title}</strong>
          <small>
            {url ? siteName(url) : "Case file"} ·{" "}
            {sourceStates[source.status] || source.status}
            {source.reviewNeeded ? " · Needs review" : ""}
          </small>
        </span>
      </button>
      {href && (
        <a
          className="source-open icon-button"
          href={href}
          target={url ? "_blank" : undefined}
          rel={url ? "noopener noreferrer" : undefined}
          download={file?.label}
          aria-label={`${url ? "Open website" : "Download file"}: ${title}`}
          title={url ? "Open website in a new tab" : "Download file"}
        >
          {url ? <ArrowUpRight size={16} /> : <Download size={16} />}
        </a>
      )}
    </div>
  );
}
const MarkdownSources = createContext<{
  chatId?: string;
  files: ChatAttachment[];
  sources: RunSource[];
}>({ files: [], sources: [] });

function CaseLink(props: { href?: unknown; children?: unknown }) {
  const { chatId, files, sources } = useContext(MarkdownSources);
  const href = typeof props.href === "string" ? props.href : undefined;
  const children = props.children as ReactNode;
  const url = sourceUrl(href);
  const file = !url ? attachmentLink(href, chatId, files) : undefined;
  const source = url
    ? sources.find(
        (s) =>
          s.favicon &&
          sourceUrl(s.url) &&
          new URL(s.url!).origin === new URL(url).origin,
      )
    : undefined;
  return url ? (
    <a
      className="citation-link"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={`Open ${siteName(url)}`}
    >
      <SiteIcon url={url} favicon={source?.favicon} size={12} />
      <span>{children}</span>
      <ArrowUpRight size={11} aria-hidden="true" />
    </a>
  ) : file ? (
    <a className="citation-link" href={file.url} download={file.label}>
      <FileIcon name={file.label} size={13} />
      {children}
      <Download size={11} />
    </a>
  ) : (
    <span>{children}</span>
  );
}
const markdownComponents = { a: CaseLink, img: () => <span>[image]</span> };

// Mark bare filenames as relative links before Markdown URL validation.
// CaseLink still resolves them only against this chat's supplied attachments.
type MarkdownNode = { type?: string; url?: string; children?: MarkdownNode[] };
function relativeFileLinks() {
  return function visit(node: MarkdownNode) {
    if (
      (node.type === "link" || node.type === "definition") &&
      node.url &&
      !/^(?:[a-z][a-z\d+.-]*:|\/|\.)/i.test(node.url)
    )
      node.url = `./${node.url}`;
    node.children?.forEach(visit);
  };
}
const remarkPlugins = [
  ...Object.values(defaultRemarkPlugins),
  relativeFileLinks,
];

export function CaseMarkdown({
  children,
  chatId,
  files = [],
  sources = [],
}: {
  children: string;
  chatId?: string;
  files?: ChatAttachment[];
  sources?: RunSource[];
}) {
  return (
    <MarkdownSources.Provider value={{ chatId, files, sources }}>
      <MessageResponse
        skipHtml
        controls={false}
        components={markdownComponents}
        remarkPlugins={remarkPlugins}
      >
        {children}
      </MessageResponse>
    </MarkdownSources.Provider>
  );
}
export function LinkedText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  let end = 0;
  for (const match of text.matchAll(/https?:\/\/[^\s<>"`]+/gi)) {
    const raw = match[0].replace(/[.,;!?)]+$/, "");
    const url = sourceUrl(raw);
    if (!url) continue;
    parts.push(
      text.slice(end, match.index),
      <a
        key={match.index}
        href={url}
        className="plain-source-link"
        target="_blank"
        rel="noopener noreferrer"
      >
        {raw}
        <ArrowUpRight size={11} aria-hidden="true" />
      </a>,
    );
    end = match.index! + raw.length;
  }
  parts.push(text.slice(end));
  return <>{parts}</>;
}
