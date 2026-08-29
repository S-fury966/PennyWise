import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Search, ArrowUpDown } from "lucide-react";
import type { Transaction } from "../api";

type SortKey = "order_id" | "match_status" | "confidence_score";
type SortDir = "asc" | "desc";

const STATUS_COLORS: Record<string, string> = {
  MATCHED: "bg-success/20 text-success",
  RESOLVED_WITH_REASONING: "bg-warning/20 text-warning",
  EXCEPTION: "bg-danger/20 text-danger",
};

export default function TransactionTable({ transactions }: { transactions: Transaction[] }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("order_id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let list = [...transactions];
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(t =>
        t.order_id.toLowerCase().includes(q) ||
        (t.override_reason || "").toLowerCase().includes(q) ||
        (t.explanation || "").toLowerCase().includes(q)
      );
    }
    if (statusFilter) list = list.filter(t => t.match_status === statusFilter);
    list.sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const cmp = typeof av === "number" ? av - (bv as number) : String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [transactions, search, statusFilter, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("asc"); }
  }

  const SortIcon = ({ k }: { k: SortKey }) => (
    <ArrowUpDown className={`inline h-3 w-3 ml-1 ${sortKey === k ? "text-accent" : "text-text-muted"}`} />
  );

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-border bg-surface overflow-hidden">
      <div className="p-4 border-b border-border flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search order ID, reason, explanation..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-background border border-border text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-background border border-border text-text-primary text-sm focus:outline-none focus:border-accent"
        >
          <option value="">All statuses</option>
          <option value="MATCHED">MATCHED</option>
          <option value="RESOLVED_WITH_REASONING">RESOLVED</option>
          <option value="EXCEPTION">EXCEPTION</option>
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text-secondary text-left">
              <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort("order_id")}>
                Order ID <SortIcon k="order_id" />
              </th>
              <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort("match_status")}>
                Status <SortIcon k="match_status" />
              </th>
              <th className="px-4 py-3 cursor-pointer select-none" onClick={() => toggleSort("confidence_score")}>
                Confidence <SortIcon k="confidence_score" />
              </th>
              <th className="px-4 py-3">Override</th>
              <th className="px-4 py-3 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(t => (
              <tr
                key={t.order_id}
                className={`border-b border-border/50 cursor-pointer transition-colors hover:bg-surface-hover ${expanded === t.order_id ? "bg-surface-hover" : ""}`}
                onClick={() => setExpanded(expanded === t.order_id ? null : t.order_id)}
              >
                <td className="px-4 py-3 font-mono text-xs text-accent-light">{t.order_id}</td>
                <td className="px-4 py-3">
                  <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[t.match_status] || "bg-surface text-text-muted"}`}>
                    {t.match_status}
                  </span>
                </td>
                <td className="px-4 py-3 text-text-primary">
                  {t.confidence_score != null ? (t.confidence_score * 100).toFixed(1) + "%" : "—"}
                </td>
                <td className="px-4 py-3 text-text-secondary text-xs">
                  {t.override_reason || "—"}
                </td>
                <td className="px-4 py-3 text-text-muted">
                  {expanded === t.order_id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {expanded && (() => {
          const t = filtered.find(x => x.order_id === expanded);
          if (!t) return null;
          return (
            <motion.div
              key={t.order_id}
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="border-t border-border bg-background/50 overflow-hidden"
            >
              <div className="p-5 space-y-3">
                <div className="flex items-center gap-3 text-xs text-text-secondary">
                  <span>Amount: {(t.amount_score ?? 0).toFixed(2)}</span>
                  <span>Timing: {(t.timing_score ?? 0).toFixed(2)}</span>
                  <span>Reference: {(t.reference_score ?? 0).toFixed(2)}</span>
                  <span className="text-text-muted ml-auto">Source: {t.explanation_source}</span>
                </div>
                <p className="text-sm text-text-primary leading-relaxed">{t.explanation}</p>
              </div>
            </motion.div>
          );
        })()}
      </AnimatePresence>

      <div className="px-4 py-2 text-xs text-text-muted border-t border-border">
        Showing {filtered.length} of {transactions.length} transactions
      </div>
    </motion.div>
  );
}
