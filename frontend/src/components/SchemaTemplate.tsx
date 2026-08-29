import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Download, ChevronDown, ChevronRight } from "lucide-react";

interface SchemaTemplate {
  required_columns: string[];
  example_row: Record<string, any>;
  constrained_fields: Record<string, string[]>;
}

interface SchemaResponse {
  ledger: SchemaTemplate;
  gateway: SchemaTemplate;
  bank: SchemaTemplate;
}

const FILE_LABELS: Record<string, string> = {
  ledger: "Internal Order Ledger",
  gateway: "Gateway Settlement Report",
  bank: "Bank Statement",
};

const FILE_ICONS: Record<string, string> = {
  ledger: "📒",
  gateway: "💳",
  bank: "🏦",
};

export default function SchemaTemplate() {
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [openFiles, setOpenFiles] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch("/api/schema-template")
      .then(r => r.json())
      .then(setSchema)
      .catch(console.error);
  }, []);

  function toggleFile(fileType: string) {
    setOpenFiles(prev => ({ ...prev, [fileType]: !prev[fileType] }));
  }

  async function downloadTemplate(fileType: string) {
    const res = await fetch(`/api/schema-template/download?file=${fileType}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileType}_template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!schema) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-surface overflow-hidden"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-6 py-4 flex items-center gap-3 text-left hover:bg-surface-hover transition-colors cursor-pointer"
      >
        <BookOpen className="h-5 w-5 text-accent" />
        <span className="text-sm font-semibold text-text-primary">Target Schema Reference</span>
        <span className="text-xs text-text-muted ml-auto">
          {expanded ? "click to collapse" : "click to view required columns"}
        </span>
        {expanded
          ? <ChevronDown className="h-4 w-4 text-text-muted" />
          : <ChevronRight className="h-4 w-4 text-text-muted" />
        }
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
              <p className="text-xs text-text-secondary">
                The normalization layer will attempt to auto-map your columns, but these are the exact target schemas.
                If auto-mapping can't resolve a column, you'll be asked to confirm the mapping manually.
              </p>

              {(Object.entries(schema) as [string, SchemaTemplate][]).map(([fileType, tmpl]) => (
                <div key={fileType} className="rounded-lg border border-border overflow-hidden">
                  <button
                    onClick={() => toggleFile(fileType)}
                    className="w-full px-4 py-3 flex items-center gap-2 text-left hover:bg-surface-hover transition-colors cursor-pointer"
                  >
                    <span className="text-base">{FILE_ICONS[fileType]}</span>
                    <span className="text-sm font-medium text-text-primary">{FILE_LABELS[fileType]}</span>
                    <span className="text-xs text-text-muted ml-2">
                      {tmpl.required_columns.length} required columns
                    </span>
                    <button
                      onClick={e => { e.stopPropagation(); downloadTemplate(fileType); }}
                      className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded text-xs text-accent hover:bg-accent/10 transition-colors cursor-pointer"
                    >
                      <Download className="h-3 w-3" />
                      Download template
                    </button>
                    {openFiles[fileType]
                      ? <ChevronDown className="h-4 w-4 text-text-muted" />
                      : <ChevronRight className="h-4 w-4 text-text-muted" />
                    }
                  </button>

                  <AnimatePresence>
                    {openFiles[fileType] && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="px-4 pb-4 space-y-3">
                          {/* Required columns */}
                          <div>
                            <div className="text-xs font-semibold text-text-secondary mb-1.5">Required Columns</div>
                            <div className="flex flex-wrap gap-1.5">
                              {tmpl.required_columns.map(col => (
                                <span key={col} className="px-2 py-0.5 rounded bg-accent/10 text-accent text-xs font-mono">
                                  {col}
                                </span>
                              ))}
                            </div>
                          </div>

                          {/* Example row */}
                          <div>
                            <div className="text-xs font-semibold text-text-secondary mb-1.5">Example Row</div>
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="border-b border-border">
                                    {tmpl.required_columns.map(col => (
                                      <th key={col} className="px-2 py-1.5 text-left text-text-secondary font-medium whitespace-nowrap">
                                        {col}
                                      </th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  <tr>
                                    {tmpl.required_columns.map(col => (
                                      <td key={col} className="px-2 py-1.5 text-text-primary font-mono whitespace-nowrap">
                                        {String(tmpl.example_row[col] ?? "")}
                                      </td>
                                    ))}
                                  </tr>
                                </tbody>
                              </table>
                            </div>
                          </div>

                          {/* Constrained fields */}
                          {Object.keys(tmpl.constrained_fields).length > 0 && (
                            <div>
                              <div className="text-xs font-semibold text-text-secondary mb-1.5">Accepted Values</div>
                              <div className="space-y-1">
                                {Object.entries(tmpl.constrained_fields).map(([field, values]) => (
                                  <div key={field} className="flex items-center gap-2 text-xs">
                                    <span className="font-mono text-text-primary">{field}:</span>
                                    <div className="flex gap-1">
                                      {values.map(v => (
                                        <span key={v} className="px-1.5 py-0.5 rounded bg-success/10 text-success font-mono">
                                          {v}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
