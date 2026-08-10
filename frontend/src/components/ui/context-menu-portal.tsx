"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

export interface ContextMenuItem {
  label:    string;
  icon?:    React.ReactNode;
  danger?:  boolean;
  onClick:  () => void;
}

interface Props {
  x:       number;
  y:       number;
  items:   ContextMenuItem[];
  onClose: () => void;
}

export function ContextMenuPortal({ x, y, items, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent | KeyboardEvent) {
      if (e instanceof KeyboardEvent && e.key !== "Escape") return;
      if (e instanceof MouseEvent && ref.current?.contains(e.target as Node)) return;
      onClose();
    }
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown",   handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown",   handler);
    };
  }, [onClose]);

  // Ajusta posición si se sale de la pantalla
  const style: React.CSSProperties = {
    position: "fixed",
    top:  y,
    left: x,
    zIndex: 9999,
  };

  return createPortal(
    <div ref={ref} style={style}
      className="min-w-[160px] rounded-[0.75rem] border border-musgo/30 bg-carbon shadow-2xl py-1 overflow-hidden">
      {items.map((item, i) => (
        <button
          key={i}
          onClick={() => { item.onClick(); onClose(); }}
          className={cn(
            "w-full flex items-center gap-2.5 px-3 py-2 font-mono text-xs transition-colors text-left",
            item.danger
              ? "text-red-400/70 hover:bg-red-900/20 hover:text-red-400"
              : "text-crema/60 hover:bg-musgo/15 hover:text-crema/90"
          )}
        >
          {item.icon && <span className="shrink-0">{item.icon}</span>}
          {item.label}
        </button>
      ))}
    </div>,
    document.body
  );
}
