import { useState, useRef, useEffect, type FormEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, Send, Loader2, ChevronDown, ChevronRight, Search } from "lucide-react";
import { askQuestion } from "../api";
import type { Transaction } from "../api";

interface QAEntry {
  question: string;
  answer: string;
  matchType: string;
  transactions: Transaction[];
}

const STATUS_COLORS: Record<string, string> = {
  MATCHED: "bg-success/20 text-success",
  RESOLVED_WITH_REASONING: "bg-warning/20 text-warning",
  EXCEPTION: "bg-danger/20 text-danger",
};

const EXAMPLE_QUESTIONS = [
  "Why wasn't ORD10027 settled?",
  "Which transactions have duplicate UTRs?",
  "Show me all exceptions",
  "Why was ORD10045 flagged?",
  "What transactions are resolved with reasoning?",
];

export default function NaturalLanguageQA() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<QAEntry[]>([]);
  const [expandedTxn, setExpandedTxn] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || loading) return;

    setInput("");
    setLoading(true);

    try {
      const res = await askQuestion(q);
      setHistory(prev => [...prev, {
        question: q,
        answer: res.answer,
        matchType: res.match_type,
        transactions: res.matched_transactions,
      }]);
    } catch (err: any) {
      setHistory(prev => [...prev, {
        question: q,
        answer: `Error: ${err?.message || "Failed to get answer"}`,
        matchType: "error",
        transactions: [],
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleExampleClick(q: string) {
    setInput(q);
    inputRef.current?.focus();
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-surface overflow-hidden"
    >
      {/* Header */}
      <div className="px-6 py-4 border-b border-border flex items-center gap-3">
        <MessageCircle className="h-5 w-5 text-accent" />
        <span className="text-sm font-semibold text-text-primary">Ask About Your Data</span>
        <span className="text-xs text-text-muted ml-auto">
          e.g. "Why wasn't ORD10027 settled?"
        </span>
      </div>

      {/* Chat area */}
      <div className="max-h-[500px] overflow-y-auto">
        {/* Empty state */}
        {history.length === 0 && !loading && (
          <div className="px-6 py-8 text-center space-y-4">
            <Search className="h-8 w-8 text-text-muted mx-auto" />
            <p className="text-sm text-text-secondary">
              Ask a natural-language question about any transaction, exception, or reconciliation result.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => handleExampleClick(q)}
                  className="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary hover:border-accent hover:text-accent transition-colors cursor-pointer"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Q&A history */}
        {history.map((entry, i) => (
          <div key={i} className="border-b border-border/50 last:border-b-0">
            {/* Question */}
            <div className="px-6 py-3 bg-background/50">
              <div className="flex items-start gap-2">
                <span className="text-xs font-bold text-accent mt-0.5 shrink-0">Q</span>
                <span className="text-sm text-text-primary">{entry.question}</span>
              </div>
            </div>

            {/* Answer */}
            <div className="px-6 py-4">
              <div className="flex items-start gap-2">
                <span className="text-xs font-bold text-success mt-0.5 shrink-0">A</span>
                <div className="flex-1 min-w-0">
                  <div
                    className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap prose-sm"
                    dangerouslySetInnerHTML={{
                      __html: entry.answer
                        .replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary font-semibold">$1</strong>')
                        .replace(/\n/g, '<br />'),
                    }}
                  />

                  {/* Matched transactions */}
                  {entry.transactions.length > 0 && (
                    <div className="mt-3 space-y-1">
                      {entry.transactions.map(txn => (
                        <div key={txn.order_id} className="rounded-lg border border-border/50 overflow-hidden">
                          <button
                            onClick={() => setExpandedTxn(
                              expandedTxn === `${i}-${txn.order_id}` ? null : `${i}-${txn.order_id}`
                            )}
                            className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-surface-hover transition-colors cursor-pointer"
                          >
                            <span className="font-mono text-xs text-accent-light">{txn.order_id}</span>
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${STATUS_COLORS[txn.match_status] || ""}`}>
                              {txn.match_status}
                            </span>
                            {txn.override_reason && (
                              <span className="text-[10px] text-text-muted">{txn.override_reason}</span>
                            )}
                            <span className="ml-auto text-text-muted">
                              {expandedTxn === `${i}-${txn.order_id}`
                                ? <ChevronDown className="h-3 w-3" />
                                : <ChevronRight className="h-3 w-3" />
                              }
                            </span>
                          </button>

                          <AnimatePresence>
                            {expandedTxn === `${i}-${txn.order_id}` && (
                              <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="overflow-hidden"
                              >
                                <div className="px-3 pb-3 space-y-2 border-t border-border/50 pt-2">
                                  <div className="flex gap-4 text-xs text-text-secondary">
                                    <span>Confidence: {txn.confidence_score != null ? `${(txn.confidence_score * 100).toFixed(1)}%` : "—"}</span>
                                    <span>Amount: {txn.amount_score?.toFixed(2) ?? "—"}</span>
                                    <span>Timing: {txn.timing_score?.toFixed(2) ?? "—"}</span>
                                    <span className="ml-auto text-text-muted">Source: {txn.explanation_source}</span>
                                  </div>
                                  <p className="text-xs text-text-primary leading-relaxed">{txn.explanation}</p>
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="px-6 py-4 flex items-center gap-2 text-text-secondary">
            <Loader2 className="h-4 w-4 animate-spin text-accent" />
            <span className="text-sm">Looking up answer...</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <form onSubmit={handleSubmit} className="px-6 py-4 border-t border-border flex items-center gap-3">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={`Try "Why wasn't ORD10027 settled?" or "Show me all exceptions"`}
          className="flex-1 px-4 py-2.5 rounded-lg bg-background border border-border text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent"
        />
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-colors cursor-pointer ${
            input.trim() && !loading
              ? "bg-accent hover:bg-accent-light text-white"
              : "bg-surface text-text-muted cursor-not-allowed"
          }`}
        >
          <Send className="h-4 w-4" />
          Ask
        </button>
      </form>
    </motion.div>
  );
}
