import { useState } from "react";
import { motion } from "framer-motion";
import { Play, Loader2, CheckCircle2, XCircle, FlaskConical, Database, Lock } from "lucide-react";
import { runReconciliation } from "../api";

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

  async function handleRun() {
    setState("running");
    setError(null);
    setResult(null);
    try {
      const res = await runReconciliation(true, 0.1, datasetSource);
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
    <div className="flex items-center gap-3">
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
          ~1-2 min (Groq free tier)...
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
