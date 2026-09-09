"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Camera,
  Download,
  FileText,
  FolderOpen,
  Globe,
  ImageIcon,
  LoaderCircle,
  Maximize2,
  Minus,
  Network,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Square,
  X,
  ExternalLink,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  boardImageUrl,
  boardPlan,
  type BoardCard,
  type BoardSnapshot,
} from "@/lib/case-board";
import type { ChatMessage } from "@/lib/chat-types";

type BoardResponse = {
  board: BoardSnapshot;
  chatId?: string;
  message?: ChatMessage;
};
const WIDTH = 1440,
  CARD = 286,
  GAP = 42,
  TOP = 354,
  ROW = 344;
function lines(text: string, width = 32, count = 3) {
  const words = text.replace(/\s+/g, " ").split(" ");
  const result: string[] = [];
  let line = "";
  for (const word of words) {
    if ((line + " " + word).length > width && line) {
      result.push(line);
      line = "";
    }
    line += (line ? " " : "") + word;
  }
  if (line) result.push(line);
  return result
    .slice(0, count)
    .map((s, i) =>
      s.length > width
        ? s.slice(0, width - 1) + "…"
        : i === count - 1 && result.length > count
          ? s.slice(0, width - 1) + "…"
          : s,
    );
}
function TextLines({
  text,
  x,
  y,
  width = 32,
  count = 3,
  size = 16,
  color = "#28352c",
}: {
  text: string;
  x: number;
  y: number;
  width?: number;
  count?: number;
  size?: number;
  color?: string;
}) {
  return (
    <text
      x={x}
      y={y}
      fill={color}
      fontSize={size}
      fontFamily="Arial, sans-serif"
    >
      {lines(text, width, count).map((s, i) => (
        <tspan key={i} x={x} dy={i ? size * 1.42 : 0}>
          {s}
        </tspan>
      ))}
    </text>
  );
}

export function CaseBoard({
  caseId,
  onClose,
  onChange,
  onOpenChat,
}: {
  caseId: string;
  onClose: () => void;
  onChange: () => void;
  onOpenChat: (chatId: string) => void;
}) {
  const [data, setData] = useState<BoardResponse>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [selected, setSelected] = useState<string>();
  const [zoom, setZoom] = useState(0.78);
  const [images, setImages] = useState<Record<string, string>>({});
  const [showSources, setShowSources] = useState(false);
  const svg = useRef<SVGSVGElement>(null),
    scroller = useRef<HTMLDivElement>(null);
  const drag = useRef<
    { x: number; y: number; left: number; top: number } | undefined
  >(undefined);
  const busy = generating || data?.message?.status === "running";
  const board = data?.board;
  const generatedUrl =
    data?.message?.generatedImage && data.chatId
      ? `/api/cases/${caseId}/board/generated?chat=${encodeURIComponent(data.chatId)}`
      : undefined;
  const showGenerated = Boolean(generatedUrl && !showSources);
  const plan = useMemo(
    () =>
      board
        ? boardPlan(
            data?.message?.status === "done" ? data.message.text : "",
            board,
          )
        : undefined,
    [board, data?.message],
  );
  const cards = useMemo(
    () =>
      plan?.order
        .map((id) => board!.cards.find((c) => c.id === id)!)
        .filter(Boolean) || [],
    [board, plan],
  );
  const focus = cards.find((c) => c.id === selected);
  const height = TOP + Math.ceil(cards.length / 4) * ROW + 70;
  const positions = new Map(
    cards.map((c, i) => [
      c.id,
      { x: 64 + (i % 4) * (CARD + GAP), y: TOP + Math.floor(i / 4) * ROW },
    ]),
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetch(`/api/cases/${caseId}/board`)
      .then(async (r) => {
        const result = await r.json();
        if (!r.ok) throw Error(result.error);
        if (active) setData(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [caseId]);
  useEffect(() => {
    if (data?.message?.status !== "running") return;
    const timer = setInterval(() => {
      void fetch(`/api/cases/${caseId}/board`)
        .then((r) => r.json())
        .then((next) => {
          if (next.board) setData(next);
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [caseId, data?.message?.status]);
  useEffect(() => {
    if (!board) return;
    const controller = new AbortController();
    void (async () => {
      const entries: Record<string, string> = {};
      for (const card of board.cards.filter((c) => c.kind === "image")) {
        try {
          const response = await fetch(boardImageUrl(caseId, card), {
            signal: controller.signal,
          });
          if (!response.ok) continue;
          const bitmap = await createImageBitmap(await response.blob());
          const canvas = document.createElement("canvas");
          canvas.width = 520;
          canvas.height = 224;
          const ctx = canvas.getContext("2d")!;
          ctx.fillStyle = "#ebe8df";
          ctx.fillRect(0, 0, 520, 224);
          const scale = Math.min(520 / bitmap.width, 224 / bitmap.height);
          ctx.drawImage(
            bitmap,
            (520 - bitmap.width * scale) / 2,
            (224 - bitmap.height * scale) / 2,
            bitmap.width * scale,
            bitmap.height * scale,
          );
          bitmap.close();
          entries[card.id] = canvas.toDataURL("image/png");
          if (!controller.signal.aborted) setImages({ ...entries });
        } catch {
          /* Keep a labelled image card when a preview is unavailable. */
        }
      }
    })();
    return () => controller.abort();
  }, [caseId, board?.createdAt]);

  async function generate() {
    setError("");
    setGenerating(true);
    setSelected(undefined);
    setShowSources(false);
    try {
      const response = await fetch(`/api/cases/${caseId}/board`, {
        method: "POST",
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.error);
      setData(result);
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  }
  async function exportPng() {
    if (showGenerated && generatedUrl) {
      const a = document.createElement("a");
      a.href = generatedUrl + "&download=1";
      a.download = "knowledge-graph.png";
      a.click();
      return;
    }
    if (!svg.current || !board) return;
    setExporting(true);
    setError("");
    let url = "";
    try {
      const copy = svg.current.cloneNode(true) as SVGSVGElement;
      copy.setAttribute("width", String(WIDTH));
      copy.setAttribute("height", String(height));
      copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      url = URL.createObjectURL(
        new Blob([new XMLSerializer().serializeToString(copy)], {
          type: "image/svg+xml;charset=utf-8",
        }),
      );
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = WIDTH * 2;
      canvas.height = height * 2;
      const context = canvas.getContext("2d")!;
      context.scale(2, 2);
      context.drawImage(image, 0, 0);
      const blob = await new Promise<Blob>((resolve, reject) =>
        canvas.toBlob(
          (b) =>
            b ? resolve(b) : reject(Error("Could not export the board.")),
          "image/png",
        ),
      );
      const download = URL.createObjectURL(blob),
        a = document.createElement("a");
      a.href = download;
      a.download = `${board.caseTitle.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 90)}-knowledge-graph.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(download), 1000);
    } catch {
      setError(
        "Could not export the image. Try again after the image previews finish loading.",
      );
    } finally {
      if (url) URL.revokeObjectURL(url);
      setExporting(false);
    }
  }
  function fit() {
    if (scroller.current) {
      const style = getComputedStyle(scroller.current);
      const available =
        scroller.current.clientWidth -
        parseFloat(style.paddingLeft) -
        parseFloat(style.paddingRight);
      setZoom(Math.max(0.2, Math.min(0.85, available / WIDTH)));
    }
  }
  useEffect(() => {
    if (loading || !scroller.current) return;
    const observer = new ResizeObserver(fit);
    observer.observe(scroller.current);
    fit();
    return () => observer.disconnect();
  }, [caseId, loading]);
  const status = busy
    ? "ImageGen is creating the case board…"
    : data?.message?.status === "error"
      ? "ImageGen could not complete the board · source cards are available"
      : data?.message?.status === "stopped"
        ? "Generation stopped · recorded material is still available"
        : generatedUrl
          ? "ImageGen visual summary · verify against source records"
          : data?.message?.status === "done"
            ? "Assistant layout unavailable · showing recorded material"
            : "Preview from saved case material";
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="case-board-dialog" showCloseButton={false}>
        <header className="case-board-header">
          <div className="case-board-heading">
            <span className="board-heading-icon">
              <Network size={23} />
            </span>
            <div>
              <DialogTitle>Case knowledge graph</DialogTitle>
              <DialogDescription>
                {board?.caseTitle || "Loading case…"}
              </DialogDescription>
            </div>
          </div>
          <div className="board-header-actions">
            <button
              className="board-action"
              onClick={exportPng}
              disabled={!cards.length || busy || exporting}
            >
              {exporting ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Download size={15} />
              )}
              <span>
                {showGenerated ? "Download image" : "Export source cards"}
              </span>
            </button>
            <button
              className="icon-button"
              aria-label="Close knowledge graph"
              onClick={onClose}
            >
              <X size={20} />
            </button>
          </div>
        </header>
        <div className="board-toolbar">
          <div className="board-status">
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <ShieldCheck size={15} />
            )}
            <span>{status}</span>
          </div>
          <div className="board-tools">
            <button
              className="icon-button"
              onClick={() => setZoom((z) => Math.max(0.2, z - 0.1))}
              aria-label="Zoom out board"
            >
              <Minus size={16} />
            </button>
            <span>{Math.round(zoom * 100)}%</span>
            <button
              className="icon-button"
              onClick={() => setZoom((z) => Math.min(1.6, z + 0.1))}
              aria-label="Zoom in board"
            >
              <Plus size={16} />
            </button>
            <button
              className="icon-button"
              onClick={fit}
              aria-label="Fit board width"
            >
              <Maximize2 size={16} />
            </button>
            {busy && data?.chatId ? (
              <button
                className="board-action"
                onClick={() =>
                  void fetch(`/api/chat/${data.chatId}`, { method: "DELETE" })
                }
              >
                <Square size={13} />
                Stop
              </button>
            ) : (
              <button
                className="board-generate"
                onClick={generate}
                disabled={!cards.length || loading}
              >
                {data?.message ? (
                  <RefreshCw size={15} />
                ) : (
                  <Sparkles size={15} />
                )}{" "}
                {data?.message
                  ? "Regenerate with ImageGen"
                  : "Generate with ImageGen"}
              </button>
            )}
          </div>
        </div>
        {error && (
          <p className="board-error" role="alert">
            {error}
          </p>
        )}
        {generatedUrl && (
          <div
            className="board-view-tabs"
            role="tablist"
            aria-label="Knowledge graph views"
          >
            <button
              role="tab"
              aria-selected={!showSources}
              onClick={() => setShowSources(false)}
            >
              <ImageIcon size={14} />
              ImageGen image
            </button>
            <button
              role="tab"
              aria-selected={showSources}
              onClick={() => setShowSources(true)}
            >
              <Network size={14} />
              Source cards
            </button>
            <span>
              Generated illustrations may contain mistakes; originals remain in
              the source cards.
            </span>
          </div>
        )}
        <div className="board-stage">
          <div
            ref={scroller}
            className="board-scroll"
            onPointerDown={(event) => {
              if (
                event.button !== 0 ||
                (event.target as Element).closest("[data-board-card]")
              )
                return;
              drag.current = {
                x: event.clientX,
                y: event.clientY,
                left: event.currentTarget.scrollLeft,
                top: event.currentTarget.scrollTop,
              };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (!drag.current) return;
              event.currentTarget.scrollLeft =
                drag.current.left - (event.clientX - drag.current.x);
              event.currentTarget.scrollTop =
                drag.current.top - (event.clientY - drag.current.y);
            }}
            onPointerUp={() => {
              drag.current = undefined;
            }}
            onPointerCancel={() => {
              drag.current = undefined;
            }}
          >
            {loading ? (
              <div className="board-empty">
                <LoaderCircle size={32} className="spin" />
                Loading case material…
              </div>
            ) : !cards.length ? (
              <div className="board-empty">
                <FolderOpen size={42} />
                <h2>Your case board starts here</h2>
                <p>
                  Add case conversations, source findings or images to this
                  folder. The board will connect the saved material.
                </p>
              </div>
            ) : showGenerated ? (
              <div className="imagegen-board-view">
                <img
                  src={generatedUrl}
                  alt="ImageGen case knowledge graph"
                  draggable={false}
                  style={{ width: WIDTH * zoom, maxWidth: "none" }}
                />
                <div className="imagegen-card-links" data-board-card>
                  <strong>Inspect source records</strong>
                  {cards.map((card) => (
                    <button key={card.id} onClick={() => setSelected(card.id)}>
                      <span>{card.id}</span>
                      {card.title}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <svg
                ref={svg}
                aria-label="Case crime board"
                role="group"
                width={WIDTH * zoom}
                height={height * zoom}
                viewBox={`0 0 ${WIDTH} ${height}`}
              >
                <defs>
                  <pattern
                    id="board-cork"
                    width="24"
                    height="24"
                    patternUnits="userSpaceOnUse"
                  >
                    <rect width="24" height="24" fill="#8c6c48" />
                    <circle cx="4" cy="7" r="1" fill="#aa8862" opacity=".48" />
                    <circle
                      cx="18"
                      cy="19"
                      r=".8"
                      fill="#594632"
                      opacity=".32"
                    />
                    <path
                      d="M12 3l2 2M2 20l3-1"
                      stroke="#785b3d"
                      opacity=".5"
                    />
                  </pattern>
                  <filter
                    id="board-shadow"
                    x="-20%"
                    y="-20%"
                    width="150%"
                    height="150%"
                  >
                    <feDropShadow
                      dx="1"
                      dy="6"
                      stdDeviation="5"
                      floodOpacity=".22"
                    />
                  </filter>
                  <radialGradient id="board-pin">
                    <stop stopColor="#e7b2a1" />
                    <stop offset=".45" stopColor="#ba5849" />
                    <stop offset="1" stopColor="#782d2c" />
                  </radialGradient>
                </defs>
                <rect
                  width={WIDTH}
                  height={height}
                  rx="8"
                  fill="url(#board-cork)"
                />
                <rect
                  x="8"
                  y="8"
                  width={WIDTH - 16}
                  height={height - 16}
                  rx="4"
                  fill="none"
                  stroke="#4c3c2d"
                  strokeWidth="16"
                />
                <text
                  x="66"
                  y="68"
                  fill="#f3e8d7"
                  fontSize="13"
                  fontFamily="Arial"
                  letterSpacing="3"
                >
                  DARKNETRA / CASE CONNECTIONS
                </text>
                <text
                  x={WIDTH - 66}
                  y="68"
                  textAnchor="end"
                  fill="#e0d0ba"
                  fontSize="12"
                  fontFamily="Arial"
                >
                  {board?.createdAt.slice(0, 10)} · {cards.length} CARDS
                  {board?.truncated ? " · PARTIAL SNAPSHOT" : ""}
                </text>
                {cards.map((card) => {
                  const p = positions.get(card.id)!;
                  return (
                    <path
                      key={`root-${card.id}`}
                      d={`M720 280 C720 ${p.y - 80},${p.x + CARD / 2} ${p.y - 70},${p.x + CARD / 2} ${p.y + 8}`}
                      fill="none"
                      stroke="#cdb693"
                      strokeWidth="1.4"
                      opacity=".48"
                    />
                  );
                })}
                {[...(board?.connections || []), ...(plan?.links || [])].map(
                  (link, i) => {
                    const a = positions.get(link.from),
                      b = positions.get(link.to);
                    if (!a || !b) return null;
                    return (
                      <g key={`${link.from}-${link.to}-${i}`}>
                        <title>
                          {link.suggested
                            ? "Suggested link: "
                            : "Recorded link: "}
                          {link.label}. {link.reason}
                        </title>
                        <path
                          d={`M${a.x + CARD / 2} ${a.y + 10} Q${(a.x + b.x + CARD) / 2} ${Math.min(a.y, b.y) - 90} ${b.x + CARD / 2} ${b.y + 10}`}
                          fill="none"
                          stroke={link.suggested ? "#b5d4e0" : "#963f39"}
                          strokeWidth="2.8"
                          strokeDasharray={link.suggested ? "8 6" : undefined}
                        />
                      </g>
                    );
                  },
                )}
                <g transform="translate(472 98)" filter="url(#board-shadow)">
                  <rect width="496" height="192" rx="3" fill="#243d34" />
                  <rect
                    x="12"
                    y="12"
                    width="472"
                    height="168"
                    fill="none"
                    stroke="#506258"
                  />
                  <ShieldCheck
                    x="28"
                    y="28"
                    width="26"
                    height="26"
                    color="#dce7d1"
                  />
                  <text
                    x="67"
                    y="47"
                    fill="#c4d3bc"
                    fontSize="12"
                    letterSpacing="2"
                    fontFamily="Arial"
                  >
                    CASE BRIEF
                  </text>
                  <TextLines
                    text={board?.caseTitle || "Case"}
                    x={28}
                    y={84}
                    width={30}
                    count={2}
                    size={25}
                    color="#f5f0df"
                  />
                  <text
                    x="28"
                    y="160"
                    fill="#c4d3bc"
                    fontSize="12"
                    fontFamily="Arial"
                  >
                    Recorded material · relationships require review
                  </text>
                  <circle cx="248" cy="8" r="7" fill="url(#board-pin)" />
                </g>
                {cards.map((card, i) => {
                  const p = positions.get(card.id)!;
                  const photo = images[card.id];
                  const Icon =
                    card.kind === "image"
                      ? Camera
                      : card.kind === "source"
                        ? Globe
                        : FileText;
                  const paper = card.kind === "note" ? "#f3e4a7" : "#fcf9f1";
                  return (
                    <g
                      key={card.id}
                      data-board-card
                      role="button"
                      tabIndex={0}
                      aria-label={`Inspect ${card.title}`}
                      onClick={() => setSelected(card.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelected(card.id);
                        }
                      }}
                      style={{ cursor: "pointer", outline: "none" }}
                      transform={`translate(${p.x} ${p.y}) rotate(${i % 3 === 0 ? -1 : i % 3 === 1 ? 1 : 0.2} ${CARD / 2} 150)`}
                    >
                      <rect
                        width={CARD}
                        height="298"
                        rx="3"
                        fill={paper}
                        stroke={selected === card.id ? "#254e43" : "#d3caba"}
                        strokeWidth={selected === card.id ? 3 : 1}
                        filter="url(#board-shadow)"
                      />
                      <rect
                        x="19"
                        y="22"
                        width="30"
                        height="30"
                        rx="7"
                        fill={card.kind === "note" ? "#e6d28b" : "#e7eadf"}
                      />
                      {card.favicon ? (
                        <image
                          href={card.favicon}
                          x="25"
                          y="28"
                          width="18"
                          height="18"
                        />
                      ) : (
                        <Icon
                          x="25"
                          y="28"
                          width="18"
                          height="18"
                          color="#536548"
                        />
                      )}
                      <text
                        x="59"
                        y="42"
                        fontFamily="Arial"
                        fontSize="10"
                        fill="#788069"
                        letterSpacing="1.3"
                      >
                        {card.kind.toUpperCase()} / {card.id.toUpperCase()}
                      </text>
                      <TextLines
                        text={card.title}
                        x={20}
                        y={79}
                        count={2}
                        width={28}
                        size={16}
                      />
                      {photo ? (
                        <>
                          <image
                            href={photo}
                            x="17"
                            y="112"
                            width="252"
                            height="112"
                            preserveAspectRatio="xMidYMid meet"
                          />
                          <rect
                            x="17"
                            y="112"
                            width="252"
                            height="112"
                            fill="none"
                            stroke="#ddd7c8"
                          />
                        </>
                      ) : (
                        <>
                          <line
                            x1="20"
                            y1="116"
                            x2="266"
                            y2="116"
                            stroke="#ded6c1"
                          />
                          <TextLines
                            text={
                              card.excerpt ||
                              "Open the source to inspect the recorded material."
                            }
                            x={20}
                            y={141}
                            width={35}
                            count={4}
                            size={12}
                            color="#66705e"
                          />
                          {card.kind === "image" && (
                            <ImageIcon
                              x="130"
                              y="199"
                              width="24"
                              height="24"
                              color="#829076"
                            />
                          )}
                        </>
                      )}
                      <line
                        x1="20"
                        y1="242"
                        x2="266"
                        y2="242"
                        stroke="#ded6c1"
                      />
                      <circle
                        cx="25"
                        cy="263"
                        r="3"
                        fill={
                          card.status === "retrieved" ||
                          card.status === "analysed"
                            ? "#658555"
                            : "#b99047"
                        }
                      />
                      <TextLines
                        text={card.status}
                        x={36}
                        y={267}
                        count={1}
                        width={31}
                        size={11}
                        color="#66705e"
                      />
                      <circle
                        cx={CARD / 2}
                        cy="8"
                        r="7"
                        fill="url(#board-pin)"
                      />
                    </g>
                  );
                })}
                <text
                  x="65"
                  y={height - 37}
                  fill="#ecdfca"
                  fontSize="11"
                  fontFamily="Arial"
                >
                  Solid red: recorded reference · Dashed blue: assistant
                  suggestion · Pale thread: included in this case · No
                  connection confirms wrongdoing
                </text>
              </svg>
            )}
          </div>
          {focus && (
            <aside className="board-inspector" aria-label="Board card details">
              <header>
                <span>
                  {focus.kind} · {focus.id}
                </span>
                <button
                  className="icon-button"
                  aria-label="Close card details"
                  onClick={() => setSelected(undefined)}
                >
                  <X size={16} />
                </button>
              </header>
              {images[focus.id] && (
                <img src={images[focus.id]} alt={focus.title} />
              )}
              <h3>{focus.title}</h3>
              <span className="board-evidence-status">{focus.status}</span>
              <p className="board-excerpt">{focus.excerpt}</p>
              {plan?.notes
                .filter((n) => n.cardId === focus.id)
                .map((note, i) => (
                  <section key={i}>
                    <h4>
                      <Sparkles size={13} />
                      Assistant review note
                    </h4>
                    <p>{note.text}</p>
                  </section>
                ))}
              {[...(board?.connections || []), ...(plan?.links || [])]
                .filter((l) => l.from === focus.id || l.to === focus.id)
                .map((link, i) => (
                  <section key={i}>
                    <h4>
                      {link.suggested
                        ? "Suggested link · review required"
                        : "Recorded reference"}
                    </h4>
                    <button
                      className="board-linked-card"
                      onClick={() =>
                        setSelected(
                          link.from === focus.id ? link.to : link.from,
                        )
                      }
                    >
                      {link.label} →{" "}
                      {
                        cards.find(
                          (c) =>
                            c.id ===
                            (link.from === focus.id ? link.to : link.from),
                        )?.title
                      }
                    </button>
                    {link.reason && <p>{link.reason}</p>}
                  </section>
                ))}
              {focus.sha256 && (
                <section>
                  <h4>Original response / file SHA-256</h4>
                  <code>{focus.sha256}</code>
                </section>
              )}
              <div className="board-inspector-links">
                <button onClick={() => onOpenChat(focus.chatId)}>
                  <FileText size={14} />
                  Open source conversation
                </button>
                {focus.url && (
                  <a href={focus.url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink size={14} />
                    Open source website
                  </a>
                )}
                {focus.file && (
                  <a
                    href={`/api/chat/${focus.chatId}/files?name=${encodeURIComponent(focus.file)}`}
                    download
                  >
                    <Download size={14} />
                    Download original file
                  </a>
                )}
              </div>
            </aside>
          )}
        </div>
        <footer className="board-footer">
          <span>
            <span className="board-legend-line" />
            Recorded reference
          </span>
          <span>
            <span className="board-legend-line suggested" />
            Suggested link
          </span>
          <span>
            Click cards to inspect · Drag the board to move
            {board?.truncated
              ? " · Showing a partial snapshot of this case"
              : ""}
          </span>
        </footer>
      </DialogContent>
    </Dialog>
  );
}
