import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { motion } from "framer-motion";
import type { Summary } from "../api";

const COLORS = [
  "#ef4444", "#f59e0b", "#3b82f6", "#22c55e",
  "#8b5cf6", "#ec4899", "#06b6d4", "#f97316", "#6366f1",
];

const LABELS: Record<string, string> = {
  DUPLICATE_UTR_ERROR: "Duplicate UTR",
  REFUND_NOT_REFLECTED: "Refund Not Reflected",
  ORPHAN_NO_GATEWAY_MATCH: "Orphan (no gateway)",
  ORPHAN_NO_LEDGER_MATCH: "Orphan (no ledger)",
  UNVERIFIED_PARTIAL: "Unverified Partial",
  UNEXPLAINED_AMOUNT_GAP: "Amount Gap",
  LOW_CONFIDENCE: "Low Confidence",
};

export default function ExceptionChart({ summary }: { summary: Summary | null }) {
  if (!summary) return <div className="h-72 rounded-xl bg-surface animate-pulse" />;

  const breakdown = summary.exception_breakdown || {};
  const data = Object.entries(breakdown)
    .map(([key, count]) => ({ name: LABELS[key] || key, value: count, rawKey: key }))
    .filter(d => d.value > 0);

  if (data.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-xl border border-border bg-surface p-6"
      >
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-4">Exception Breakdown</h3>
        <div className="flex items-center justify-center h-48 text-text-muted text-sm">
          No exceptions — all transactions matched.
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-surface p-6"
    >
      <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-4">Exception Breakdown</h3>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={90}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="none" />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: "#1a1a24", border: "1px solid #2a2a3a", borderRadius: 8, color: "#f0f0f5" }}
            formatter={(value, name) => [`${value} txn${Number(value) !== 1 ? "s" : ""}`, String(name)]}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "#8888a0" }}
            formatter={(value: string) => <span style={{ color: "#8888a0" }}>{value}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
