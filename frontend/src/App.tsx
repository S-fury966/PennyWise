import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Database, FlaskConical } from "lucide-react";
import { fetchSummary, fetchTransactions } from "./api";
import type { Summary, Transaction } from "./api";
import KPICards from "./components/KPICards";
import ExceptionChart from "./components/ExceptionChart";
import ConfidenceHistogram from "./components/ConfidenceHistogram";
import TransactionTable from "./components/TransactionTable";
import FlaggedForReview from "./components/FlaggedForReview";
import RunButton from "./components/RunButton";
import DatasetUpload from "./components/DatasetUpload";
import SchemaTemplate from "./components/SchemaTemplate";
import NaturalLanguageQA from "./components/NaturalLanguageQA";

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [datasetSource, setDatasetSource] = useState<"sample" | "custom">("sample");
  const [customDataReady, setCustomDataReady] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [s, t] = await Promise.all([fetchSummary(), fetchTransactions()]);
      setSummary(s);
      setTransactions(t.transactions);
      // Sync dataset source from what the backend reports
      if (s && "dataset_source" in s) {
        setDatasetSource((s as any).dataset_source);
      }
    } catch (e) {
      console.error("Failed to load data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  function handleUploadComplete(readyForReconciliation: boolean) {
    setCustomDataReady(readyForReconciliation);
    if (readyForReconciliation) {
      setDatasetSource("custom");
    }
    loadData();
  }

  return (
    <div className="min-h-screen bg-background p-6 max-w-[1400px] mx-auto space-y-8">
      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
      >
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">
            AI Finance Controller
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Multi-source reconciliation — ledger x gateway x bank
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Dataset source indicator */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border ${
            datasetSource === "custom"
              ? "border-accent/40 bg-accent/10 text-accent-light"
              : "border-border bg-surface text-text-secondary"
          }`}>
            {datasetSource === "custom"
              ? <Database className="h-3.5 w-3.5" />
              : <FlaskConical className="h-3.5 w-3.5" />
            }
            {datasetSource === "custom" ? "Custom Data" : "Sample Data"}
          </div>

          <RunButton
            onRunComplete={loadData}
            datasetSource={datasetSource}
            onDatasetSourceChange={setDatasetSource}
            disabled={datasetSource === "custom" && !customDataReady}
          />
        </div>
      </motion.header>

      {/* Schema reference */}
      <SchemaTemplate />

      {/* Upload section */}
      <DatasetUpload onUploadComplete={handleUploadComplete} />

      {/* KPI Cards */}
      <KPICards summary={summary} />

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ExceptionChart summary={summary} />
        <ConfidenceHistogram transactions={transactions} />
      </div>

      {/* Flagged for Review */}
      <FlaggedForReview transactions={transactions} />

      {/* Full Transaction Table */}
      <TransactionTable transactions={transactions} />

      {/* Natural Language Q&A */}
      <NaturalLanguageQA />

      {/* Loading overlay */}
      {loading && (
        <div className="fixed inset-0 bg-background/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="flex items-center gap-3 text-text-secondary">
            <div className="h-5 w-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
            Loading data...
          </div>
        </div>
      )}
    </div>
  );
}
