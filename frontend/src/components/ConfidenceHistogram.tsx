import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { motion } from "framer-motion";
import type { Transaction } from "../api";

function buildBuckets(transactions: Transaction[]) {
  const buckets = Array.from({ length: 10 }, (_, i) => ({
    range: `${(i * 10)}%`,
    label: `${i * 10}–${(i + 1) * 10}%`,
    count: 0,
  }));
  for (const t of transactions) {
    const score = t.confidence_score ?? 0;
    const idx = Math.min(Math.floor(score * 10), 9);
    buckets[idx].count++;
  }
  return buckets;
}

export default function ConfidenceHistogram({ transactions }: { transactions: Transaction[] }) {
  const buckets = buildBuckets(transactions);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-surface p-6"
    >
      <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-4">
        Confidence Distribution
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={buckets} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2a" vertical={false} />
          <XAxis dataKey="range" tick={{ fill: "#555570", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#555570", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip
            contentStyle={{ background: "#1a1a24", border: "1px solid #2a2a3a", borderRadius: 8, color: "#f0f0f5", fontSize: 12 }}
            formatter={(value) => [`${value} txn${Number(value) !== 1 ? "s" : ""}`, "Count"]}
            labelFormatter={(_label, payload) => payload?.[0]?.payload?.label || String(_label)}
          />
          <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} maxBarSize={48} />
        </BarChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
