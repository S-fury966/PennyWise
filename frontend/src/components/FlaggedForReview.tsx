import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertOctagon, ChevronDown, ChevronUp } from "lucide-react";
import type { Transaction } from "../api";

const CATEGORY_LABELS: Record<string, string> = {
  DUPLICATE_UTR_ERROR: "Duplicate UTR — possible double credit",
  REFUND_NOT_REFLECTED: "Refund not reflected across systems",
  ORPHAN_NO_GATEWAY_MATCH: "Bank credit with no gateway match",
  ORPHAN_NO_LEDGER_MATCH: "Ledger order with no gateway match",
  UNVERIFIED_PARTIAL: "Partial settlement amounts don't reconcile",
  UNEXPLAINED_AMOUNT_GAP: "Amount mismatch across sources",
  LOW_CONFIDENCE: "Multiple weak signals",
};

const CATEGORY_COLORS: Record<string, string> = {
  DUPLICATE_UTR_ERROR: "border-danger/60 bg-danger/5",
  REFUND_NOT_REFLECTED: "border-warning/60 bg-warning/5",
  ORPHAN_NO_GATEWAY_MATCH: "border-info/60 bg-info/5",
  ORPHAN_NO_LEDGER_MATCH: "border-info/60 bg-info/5",
  UNVERIFIED_PARTIAL: "border-accent/60 bg-accent/5",
  UNEXPLAINED_AMOUNT_GAP: "border-danger/60 bg-danger/5",
  LOW_CONFIDENCE: "border-text-muted/40 bg-surface",
};

export default function FlaggedForReview({ transactions }: { transactions: Transaction[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const flagged = transactions.filter(t => t.match_status === "EXCEPTION");

  if (flagged.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border-2 border-danger/40 bg-danger/5 overflow-hidden"
    >
      <div className="px-6 py-4 border-b border-danger/20 flex items-center gap-3">
        <AlertOctagon className="h-5 w-5 text-danger" />
        <div>
          <h3 className="text-base font-bold text-danger">Flagged for Review</h3>
          <p className="text-xs text-text-secondary">{flagged.length} transaction{flagged.length !== 1 ? "s" : ""} require manual attention</p>
        </div>
      </div>

      <div className="divide-y divide-danger/10">
        {flagged.map(t => {
          const cat = t.override_reason || "LOW_CONFIDENCE";
          const isExpanded = expanded === t.order_id;
          return (
            <div key={t.order_id}>
              <button
                className="w-full px-6 py-4 flex items-center gap-4 text-left hover:bg-danger/10 transition-colors"
                onClick={() => setExpanded(isExpanded ? null : t.order_id)}
              >
                <span className="font-mono text-xs text-accent-light shrink-0">{t.order_id}</span>
                <span className={`flex-1 text-xs px-2 py-0.5 rounded border ${CATEGORY_COLORS[cat] || CATEGORY_COLORS.LOW_CONFIDENCE}`}>
                  {CATEGORY_LABELS[cat] || cat}
                </span>
                <span className="text-xs text-text-muted shrink-0">
                  {t.confidence_score != null ? (t.confidence_score * 100).toFixed(0) + "%" : "—"}
                </span>
                {isExpanded
                  ? <ChevronUp className="h-4 w-4 text-text-muted shrink-0" />
                  : <ChevronDown className="h-4 w-4 text-text-muted shrink-0" />}
              </button>

              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="px-6 pb-5 pt-1 space-y-3">
                      <div className="flex gap-6 text-xs text-text-secondary">
                        <span>Amount score: {(t.amount_score ?? 0).toFixed(2)}</span>
                        <span>Timing score: {(t.timing_score ?? 0).toFixed(2)}</span>
                        <span>Reference score: {(t.reference_score ?? 0).toFixed(2)}</span>
                      </div>
                      <p className="text-sm text-text-primary leading-relaxed">{t.explanation}</p>
                      <p className="text-xs text-text-muted">Explanation source: {t.explanation_source}</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
