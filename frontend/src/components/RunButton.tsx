import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Loader2, CheckCircle2, XCircle, FlaskConical, Database, Lock, Info } from "lucide-react";
import { runReconciliation } from "../api";

type ExplanationMode = "llm" | "rule_based";

interface RunButtonProps {
  onRunComplete: () => void;
  datasetSource: "sample" | "custom";
  onDatasetSourceChange: (v: "sample" | "custom") => void;
  disabled?: boolean;
}

export default function RunButton({ onRunComplete, datasetSource, onDatasetSourceChange, disabled }: RunButtonProps) {
  const [state, setState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<{ records: number; duration: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explanationMode, setExplanationMode] = useState<ExplanationMode>("llm");
  const [showTradeoff, setShowTradeoff] = useState(false);

  async function handleRun() {
    setState("running");
    setError(null);
    setResult(null);
    try {
      const res = await runReconciliation(explanationMode === "llm", 0.1, datasetSource);
      setResult({
        records: res.run_summary.total_records,
        duration: res.run_summary.duration_seconds,
      });
      setState("done");
      onRunComplete();
      setTimeout(() => setState("idle"), 4000);
    } catch (e: any) {
      setError(e?.message || "Run failed");
      setState("error");
      setTimeout(() => setState("idle"), 5000);
    }
  }

  const isRunning = state === "running";
  const isDisabled = isRunning || disabled;

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Dataset source toggle */}
      <div className="flex rounded-lg border border-border overflow-hidden text-xs">
        <button
          onClick={() => onDatasetSourceChange("sample")}
          className={`flex items-center gap-1.5 px-3 py-2 transition-colors cursor-pointer ${
            datasetSource === "sample"
              ? "bg-accent text-white"
              : "bg-surface text-text-secondary hover:bg-surface-hover"
          }`}
        >
          <FlaskConical className="h-3.5 w-3.5" />
          Sample
        </button>
        <button
          onClick={() => onDatasetSourceChange("custom")}
          className={`flex items-center gap-1.5 px-3 py-2 transition-colors cursor-pointer ${
            datasetSource === "custom"
              ? "bg-accent text-white"
              : "bg-surface text-text-secondary hover:bg-surface-hover"
          }`}
        >
          <Database className="h-3.5 w-3.5" />
          Custom
        </button>
      </div>

      {/* Explanation mode toggle */}
      <div className="relative flex items-center">
        <div className="flex rounded-lg border border-border overflow-hidden text-xs">
          <button
            onClick={() => setExplanationMode("llm")}
            className={`px-3 py-2 transition-colors cursor-pointer ${
              explanationMode === "llm"
                ? "bg-accent text-white"
                : "bg-surface text-text-secondary hover:bg-surface-hover"
            }`}
          >
            AI Explanations
          </button>
          <button
            onClick={() => setExplanationMode("rule_based")}
            className={`px-3 py-2 transition-colors cursor-pointer ${
              explanationMode === "rule_based"
                ? "bg-accent text-white"
                : "bg-surface text-text-secondary hover:bg-surface-hover"
            }`}
          >
            Instant Explanations
          </button>
        </div>

        {/* Tradeoff info toggle */}
        <button
          onClick={() => setShowTradeoff(v => !v)}
          className="ml-1 p-1 rounded text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
          title="Compare explanation modes"
        >
          <Info className="h-3.5 w-3.5" />
        </button>

        <AnimatePresence>
          {showTradeoff && (
            <motion.div
              initial={{ opacity: 0, y: 4, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.97 }}
              className="absolute top-full left-0 mt-2 z-50 w-[380px] rounded-xl border border-border bg-surface shadow-xl p-4 text-xs text-text-secondary"
            >
              <div className="space-y-3">
                <div>
                  <h4 className="font-semibold text-text-primary mb-1">AI Explanations</h4>
                  <ul className="space-y-0.5 text-text-secondary">
                    <li>- Natural, conversational phrasing</li>
                    <li>- Takes ~1-2 minutes for a full batch (external API, rate-limited on free tier)</li>
                    <li>- Requires network access and a valid API key</li>
                    <li>- Best for: final demos, stakeholder-facing reports</li>
                  </ul>
                </div>
                <div>
                  <h4 className="font-semibold text-text-primary mb-1">Instant Explanations</h4>
                  <ul className="space-y-0.5 text-text-secondary">
                    <li>- Structured, still specific to each transaction — not generic</li>
                    <li>- Completes in seconds, no network dependency</li>
                    <li>- Fully deterministic — same input always produces the same output</li>
                    <li>- Best for: quick iteration, testing, or when API access is unreliable</li>
                  </ul>
                </div>
                <button
                  onClick={() => setShowTradeoff(false)}
                  className="w-full py-1.5 rounded bg-surface-hover text-text-muted hover:text-text-primary transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <motion.button
        onClick={handleRun}
        whileHover={{ scale: isDisabled ? 1 : 1.02 }}
        whileTap={{ scale: isDisabled ? 1 : 0.98 }}
        disabled={isDisabled}
        title={disabled ? "Upload and normalize a custom dataset first" : undefined}
        className={`
          inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold
          transition-colors cursor-pointer
          ${isDisabled
            ? "bg-surface text-text-muted cursor-not-allowed"
            : "bg-accent hover:bg-accent-light text-white"
          }
        `}
      >
        {isRunning ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Running...
          </>
        ) : state === "done" ? (
          <>
            <CheckCircle2 className="h-4 w-4 text-success" />
            Done
          </>
        ) : state === "error" ? (
          <>
            <XCircle className="h-4 w-4 text-danger" />
            Failed
          </>
        ) : disabled ? (
          <>
            <Lock className="h-4 w-4" />
            Run Reconciliation
          </>
        ) : (
          <>
            <Play className="h-4 w-4" />
            Run Reconciliation
          </>
        )}
      </motion.button>

      {isRunning && (
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-xs text-text-secondary"
        >
          {explanationMode === "llm" ? "~1-2 min (AI mode)..." : "Usually just a few seconds..."}
        </motion.span>
      )}

      {disabled && !isRunning && (
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-xs text-warning"
        >
          Upload custom data first
        </motion.span>
      )}

      {result && (
        <motion.span
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className="text-xs text-success"
        >
          {result.records} records in {result.duration}s
        </motion.span>
      )}

      {error && (
        <motion.span
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className="text-xs text-danger max-w-[200px] truncate"
        >
          {error}
        </motion.span>
      )}
    </div>
  );
}
