import * as React from "react";
import { cn } from "@/lib/utils";

const STATE_COLORS: Record<string, string> = {
  RECEIVED: "bg-slate-500/20 text-slate-300",
  TRIAGE: "bg-slate-500/20 text-slate-300",
  PLANNING: "bg-amber-500/20 text-amber-300",
  EXECUTING: "bg-sky-500/20 text-sky-300",
  SETTLEMENT: "bg-sky-500/20 text-sky-300",
  CLOSED: "bg-emerald-500/20 text-emerald-300",
  REVIEW_PENDING: "bg-amber-500/20 text-amber-300",
  INFO_PENDING: "bg-violet-500/20 text-violet-300",
  DENIED: "bg-red-500/20 text-red-300",
  ESCALATED: "bg-red-500/20 text-red-300",
  WITHDRAWN: "bg-slate-600/20 text-slate-400",
  FAILED: "bg-red-500/20 text-red-300",
};

export function Badge({
  children,
  tone,
  className,
}: {
  children: React.ReactNode;
  tone?: string;
  className?: string;
}) {
  const color = (tone && STATE_COLORS[tone]) || "bg-muted text-muted-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        color,
        className,
      )}
    >
      {children}
    </span>
  );
}
