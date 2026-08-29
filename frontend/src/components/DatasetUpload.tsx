import { useState, useRef, type RefObject } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload, CheckCircle2, XCircle, FileText, Loader2,
  ArrowRight, AlertTriangle, ChevronDown, ChevronRight,
} from "lucide-react";

interface MappingDetail {
  auto_mapped: Record<string, { source_col: string; confidence: string }>;
  unmapped_required: string[];
  unused_uploaded_columns: string[];
  file_type: string;
}

interface NeedsMappingResponse {
  status: "needs_mapping";
  message: string;
  session_id: string;
  mapping_details: Record<string, MappingDetail>;
}

interface SuccessResponse {
  status: "success";
  ready_for_reconciliation: boolean;
  message: string;
  files: Array<{ filename: string; row_count: number; unique_order_ids?: number; date_range?: { from: string; to: string } }>;
  normalization_warnings: Record<string, Array<{ row_index: number; column: string; original_value: string; reason: string }>>;
  total_warnings_applied: number;
}

interface FailedResponse {
  status: "failed";
  message: string;
  errors: Record<string, { failure_reason?: string; unresolvable_issues?: Array<{ row_index: number; column: string; original_value: string; reason: string }> }>;
}

interface DatasetUploadProps {
  onUploadComplete: (readyForReconciliation: boolean) => void;
}

const FILE_LABELS: Record<string, string> = {
  ledger_file: "Internal Order Ledger",
  gateway_file: "Gateway Settlement Report",
  bank_file: "Bank Statement",
};

export default function DatasetUpload({ onUploadComplete }: DatasetUploadProps) {
  const [ledgerFile, setLedgerFile] = useState<File | null>(null);
  const [gatewayFile, setGatewayFile] = useState<File | null>(null);
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [phase, setPhase] = useState<"select" | "analyzing" | "mapping" | "success" | "failed">("select");
  const [mappingData, setMappingData] = useState<NeedsMappingResponse | null>(null);
  const [manualMappings, setManualMappings] = useState<Record<string, Record<string, string>>>({});
  const [successData, setSuccessData] = useState<SuccessResponse | null>(null);
  const [failedData, setFailedData] = useState<FailedResponse | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [expandedWarnings, setExpandedWarnings] = useState(false);

  const ledgerRef = useRef<HTMLInputElement>(null);
  const gatewayRef = useRef<HTMLInputElement>(null);
  const bankRef = useRef<HTMLInputElement>(null);

  function FileInput({
    label, file, inputRef, onChange,
  }: {
    label: string; file: File | null;
    inputRef: RefObject<HTMLInputElement | null>;
    onChange: (f: File | null) => void;
  }) {
    return (
      <div className="flex items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={e => onChange(e.target.files?.[0] || null)}
        />
        <button
          onClick={() => inputRef.current?.click()}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm transition-colors cursor-pointer ${
            file
              ? "border-success/60 bg-success/10 text-success"
              : "border-border bg-background text-text-secondary hover:border-accent"
          }`}
        >
          <FileText className="h-4 w-4" />
          {file ? file.name : `Choose ${label}`}
        </button>
        {file && <span className="text-xs text-text-muted">{(file.size / 1024).toFixed(1)} KB</span>}
      </div>
    );
  }

  function resetState() {
    setPhase("select");
    setMappingData(null);
    setManualMappings({});
    setSuccessData(null);
    setFailedData(null);
    onUploadComplete(false);
  }

  async function handleAnalyze() {
    if (!ledgerFile || !gatewayFile || !bankFile) return;
    setPhase("analyzing");
    setFailedData(null);
    setSuccessData(null);

    const formData = new FormData();
    formData.append("ledger_file", ledgerFile);
    formData.append("gateway_file", gatewayFile);
    formData.append("bank_file", bankFile);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();

      if (res.status === 422 && data.status === "needs_mapping") {
        setMappingData(data);
        setManualMappings({});
        setPhase("mapping");
      } else if (res.ok && data.status === "success") {
        setSuccessData(data);
        setPhase("success");
        onUploadComplete(data.ready_for_reconciliation);
      } else if (res.status === 422 && data.status === "failed") {
        setFailedData(data);
        setPhase("failed");
      } else {
        setFailedData({ status: "failed", message: data.detail?.message || "Upload failed", errors: {} });
        setPhase("failed");
      }
    } catch (e: any) {
      setFailedData({ status: "failed", message: e?.message || "Network error", errors: {} });
      setPhase("failed");
    }
  }

  async function handleConfirmMapping() {
    if (!mappingData) return;
    setConfirming(true);

    const params = new URLSearchParams({ session_id: mappingData.session_id });

    for (const [field, mapping] of Object.entries(manualMappings)) {
      const jsonStr = JSON.stringify(mapping);
      if (field === "ledger_file") params.set("ledger_mapping", jsonStr);
      if (field === "gateway_file") params.set("gateway_mapping", jsonStr);
      if (field === "bank_file") params.set("bank_mapping", jsonStr);
    }

    try {
      const res = await fetch(`/api/upload/confirm-mapping?${params}`, { method: "POST" });
      const data = await res.json();

      if (res.status === 422 && data.status === "needs_mapping") {
        setMappingData(data);
        setPhase("mapping");
      } else if (res.ok && data.status === "success") {
        setSuccessData(data);
        setPhase("success");
        onUploadComplete(data.ready_for_reconciliation);
      } else if (res.status === 422 && data.status === "failed") {
        setFailedData(data);
        setPhase("failed");
      } else {
        setFailedData({ status: "failed", message: data.detail?.message || "Confirmation failed", errors: {} });
        setPhase("failed");
      }
    } catch (e: any) {
      setFailedData({ status: "failed", message: e?.message || "Network error", errors: {} });
      setPhase("failed");
    } finally {
      setConfirming(false);
    }
  }

  function setManualMapping(fileField: string, canonical: string, sourceCol: string) {
    setManualMappings(prev => ({
      ...prev,
      [fileField]: {
        ...prev[fileField],
        [canonical]: sourceCol,
      },
    }));
  }

  const allSelected = ledgerFile && gatewayFile && bankFile;

  // Check if all unmapped columns have manual mappings assigned
  function allMappingsComplete(): boolean {
    if (!mappingData) return false;
    for (const [field, detail] of Object.entries(mappingData.mapping_details)) {
      const manual = manualMappings[field] || {};
      for (const col of detail.unmapped_required) {
        if (!manual[col]) return false;
      }
    }
    return true;
  }

  const allWarnings = successData
    ? Object.entries(successData.normalization_warnings).flatMap(([field, warns]) =>
        warns.map(w => ({ ...w, file: FILE_LABELS[field] || field }))
      )
    : [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-surface overflow-hidden"
    >
      <button
        onClick={() => phase === "select" && setExpanded(!expanded)}
        className="w-full px-6 py-4 flex items-center gap-3 text-left hover:bg-surface-hover transition-colors cursor-pointer"
      >
        <Upload className="h-5 w-5 text-accent" />
        <span className="text-sm font-semibold text-text-primary">Upload Custom Dataset</span>
        {phase === "success" && (
          <CheckCircle2 className="h-4 w-4 text-success ml-1" />
        )}
        {phase === "mapping" && (
          <AlertTriangle className="h-4 w-4 text-warning ml-1" />
        )}
        <span className="text-xs text-text-muted ml-auto">
          {phase === "select" ? "CSV files — auto-normalized" : phase === "mapping" ? "needs your input" : ""}
        </span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-6 pb-6 space-y-4 border-t border-border pt-4">
              {/* Phase: Select files */}
              {phase === "select" && (
                <>
                  <p className="text-xs text-text-secondary">
                    Upload your CSV files — the system will auto-detect column names, normalize formats,
                    and only ask you to confirm if it can't resolve something automatically.
                  </p>

                  <div className="space-y-3">
                    <FileInput label="Ledger CSV" file={ledgerFile} inputRef={ledgerRef} onChange={setLedgerFile} />
                    <FileInput label="Gateway CSV" file={gatewayFile} inputRef={gatewayRef} onChange={setGatewayFile} />
                    <FileInput label="Bank CSV" file={bankFile} inputRef={bankRef} onChange={setBankFile} />
                  </div>

                  <button
                    onClick={handleAnalyze}
                    disabled={!allSelected}
                    className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors cursor-pointer ${
                      allSelected
                        ? "bg-accent hover:bg-accent-light text-white"
                        : "bg-surface text-text-muted cursor-not-allowed"
                    }`}
                  >
                    <ArrowRight className="h-4 w-4" />
                    Analyze & Normalize
                  </button>
                </>
              )}

              {/* Phase: Analyzing */}
              {phase === "analyzing" && (
                <div className="flex items-center gap-3 py-4">
                  <Loader2 className="h-5 w-5 text-accent animate-spin" />
                  <span className="text-sm text-text-secondary">Analyzing columns and normalizing values...</span>
                </div>
              )}

              {/* Phase: Needs mapping */}
              {phase === "mapping" && mappingData && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 text-warning">
                    <AlertTriangle className="h-4 w-4" />
                    <span className="text-sm font-semibold">Manual column mapping required</span>
                  </div>
                  <p className="text-xs text-text-secondary">
                    The system couldn't auto-map some columns. For each unmapped field below,
                    select which uploaded column it corresponds to.
                  </p>

                  {Object.entries(mappingData.mapping_details).map(([field, detail]) => (
                    <div key={field} className="rounded-lg border border-border p-4 space-y-3">
                      <div className="text-sm font-semibold text-text-primary">{FILE_LABELS[field]}</div>

                      {/* Auto-mapped columns */}
                      {Object.keys(detail.auto_mapped).length > 0 && (
                        <div className="text-xs text-success">
                          Auto-mapped: {Object.entries(detail.auto_mapped).map(([canon, info]) => (
                            <span key={canon} className="ml-1 font-mono">
                              {canon}←{info.source_col}
                              {info.confidence === "medium" ? " (~)" : ""}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Unmapped columns requiring manual selection */}
                      {detail.unmapped_required.length > 0 && (
                        <div className="space-y-2">
                          {detail.unmapped_required.map(canonical => (
                            <div key={canonical} className="flex items-center gap-2">
                              <span className="text-xs font-mono text-text-primary w-40 truncate" title={canonical}>
                                {canonical}
                              </span>
                              <ArrowRight className="h-3 w-3 text-text-muted flex-shrink-0" />
                              <select
                                value={manualMappings[field]?.[canonical] || ""}
                                onChange={e => setManualMapping(field, canonical, e.target.value)}
                                className="flex-1 px-2 py-1.5 rounded border border-border bg-background text-xs text-text-primary cursor-pointer"
                              >
                                <option value="">-- select a column --</option>
                                {detail.unused_uploaded_columns.map(col => (
                                  <option key={col} value={col}>{col}</option>
                                ))}
                              </select>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}

                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleConfirmMapping}
                      disabled={!allMappingsComplete() || confirming}
                      className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors cursor-pointer ${
                        allMappingsComplete() && !confirming
                          ? "bg-accent hover:bg-accent-light text-white"
                          : "bg-surface text-text-muted cursor-not-allowed"
                      }`}
                    >
                      {confirming ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Confirming...
                        </>
                      ) : (
                        <>
                          <CheckCircle2 className="h-4 w-4" />
                          Confirm Mapping & Normalize
                        </>
                      )}
                    </button>
                    <button
                      onClick={resetState}
                      className="px-4 py-2.5 rounded-lg text-sm text-text-secondary hover:bg-surface-hover transition-colors cursor-pointer"
                    >
                      Start over
                    </button>
                  </div>
                </div>
              )}

              {/* Phase: Success */}
              {phase === "success" && successData && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-3"
                >
                  <div className="rounded-lg border border-success/40 bg-success/5 p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 className="h-4 w-4 text-success" />
                      <span className="text-sm font-semibold text-success">{successData.message}</span>
                    </div>
                    <div className="space-y-1">
                      {successData.files.map(f => (
                        <div key={f.filename} className="text-xs text-text-secondary">
                          <span className="font-mono">{f.filename}</span>: {f.row_count} rows
                          {f.unique_order_ids != null && ` (${f.unique_order_ids} unique orders)`}
                          {f.date_range && ` [${f.date_range.from} to ${f.date_range.to}]`}
                        </div>
                      ))}
                    </div>
                    {successData.total_warnings_applied > 0 && (
                      <button
                        onClick={() => setExpandedWarnings(!expandedWarnings)}
                        className="mt-2 inline-flex items-center gap-1 text-xs text-warning hover:text-warning/80 cursor-pointer"
                      >
                        {expandedWarnings ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                        {successData.total_warnings_applied} formatting fixes applied automatically
                      </button>
                    )}
                  </div>

                  {/* Normalization warnings detail */}
                  <AnimatePresence>
                    {expandedWarnings && allWarnings.length > 0 && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="rounded-lg border border-border p-3 space-y-1 max-h-48 overflow-y-auto">
                          {allWarnings.map((w, i) => (
                            <div key={i} className="text-xs text-text-secondary font-mono">
                              Row {w.row_index}: {w.column} — "{w.original_value}" → {w.reason}
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <button
                    onClick={resetState}
                    className="px-4 py-2 rounded-lg text-xs text-text-secondary hover:bg-surface-hover transition-colors cursor-pointer"
                  >
                    Upload different files
                  </button>
                </motion.div>
              )}

              {/* Phase: Failed */}
              {phase === "failed" && failedData && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-3"
                >
                  <div className="rounded-lg border border-danger/40 bg-danger/5 p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <XCircle className="h-4 w-4 text-danger" />
                      <span className="text-sm font-semibold text-danger">{failedData.message}</span>
                    </div>
                    {Object.entries(failedData.errors).map(([field, err]) => (
                      <div key={field} className="text-xs text-text-secondary mt-1">
                        <span className="font-semibold">{FILE_LABELS[field] || field}:</span>{" "}
                        {err.failure_reason || err.unresolvable_issues?.map(i => `Row ${i.row_index}: ${i.reason}`).join("; ") || "Unknown error"}
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={resetState}
                    className="px-4 py-2 rounded-lg text-sm text-text-secondary hover:bg-surface-hover transition-colors cursor-pointer"
                  >
                    Start over
                  </button>
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
