import type { ReactNode } from "react";

export function StatusBadge({ children, tone = "neutral", dot = false }: {
  children: ReactNode; tone?: "neutral" | "green" | "red" | "purple" | "orange" | "blue"; dot?: boolean;
}) {
  return <span className={`badge badge-${tone}`}>{dot && <span className="status-dot" />}{children}</span>;
}
