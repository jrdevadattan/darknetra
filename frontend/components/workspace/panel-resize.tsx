"use client";
import { useEffect, useRef, useState } from "react";
import { GripVertical } from "lucide-react";

export function usePanelWidth(key: string, initial: number) {
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(key));
      if (Number.isFinite(saved) && saved >= 160 && saved <= 1000)
        setWidth(saved);
    } catch {
      /* Storage is optional. */
    }
  }, [key]);
  function resize(value: number) {
    setWidth(value);
    try {
      localStorage.setItem(key, String(value));
    } catch {
      /* Keep the current session usable. */
    }
  }
  return [width, resize] as const;
}

export function PanelResize({
  label,
  side = "right",
  width,
  onResize,
  minimum,
  maximum,
  initial,
}: {
  label: string;
  side?: "left" | "right";
  width: number;
  onResize: (width: number) => void;
  minimum: number;
  maximum: number;
  initial: number;
}) {
  const drag = useRef<{ x: number; width: number; max: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const direction = side === "right" ? 1 : -1;
  const bound = (value: number, max = maximum) =>
    Math.round(Math.min(Math.max(value, minimum), Math.max(minimum, max)));
  function limits(element: HTMLElement) {
    const panel = element.parentElement!;
    const available = panel.classList.contains("investigation-panel")
      ? panel.parentElement!.clientWidth - 320
      : window.innerWidth - 660;
    return {
      width: panel.getBoundingClientRect().width,
      max: Math.min(maximum, Math.max(minimum, available)),
    };
  }
  return (
    <div
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={minimum}
      aria-valuemax={maximum}
      aria-valuenow={bound(width)}
      aria-valuetext={`${bound(width)} pixels`}
      tabIndex={0}
      className={`panel-resize resize-${side} ${dragging ? "dragging" : ""}`}
      title="Drag to resize · Arrow keys to adjust · Double-click to reset"
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        const measured = limits(event.currentTarget);
        drag.current = { x: event.clientX, ...measured };
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(true);
      }}
      onPointerMove={(event) => {
        if (drag.current)
          onResize(
            bound(
              drag.current.width + (event.clientX - drag.current.x) * direction,
              drag.current.max,
            ),
          );
      }}
      onLostPointerCapture={() => {
        drag.current = null;
        setDragging(false);
      }}
      onPointerUp={(event) => {
        drag.current = null;
        setDragging(false);
        if (event.currentTarget.hasPointerCapture(event.pointerId))
          event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onDoubleClick={(event) =>
        onResize(bound(initial, limits(event.currentTarget).max))
      }
      onKeyDown={(event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
          return;
        event.preventDefault();
        const current = limits(event.currentTarget);
        const next =
          event.key === "Home"
            ? minimum
            : event.key === "End"
              ? current.max
              : current.width +
                (event.key === "ArrowRight" ? 1 : -1) *
                  direction *
                  (event.shiftKey ? 40 : 16);
        onResize(bound(next, current.max));
      }}
    >
      <GripVertical size={13} aria-hidden="true" />
    </div>
  );
}
