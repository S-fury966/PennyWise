import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TrendingUp, Activity, AlertTriangle, BarChart3, Clock } from "lucide-react";
import type { Summary } from "../api";

function useCountUp(target: number, duration = 1200) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (target === 0) { setValue(0); return; }
    let start = 0;
    const startTime = performance.now();
    function tick(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      start = Math.round(eased * target * 100) / 100;
      setValue(start);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }, [target, duration]);
  return value;
}

function Card({ icon: Icon, label, value, suffix, color }: {
  icon: React.ElementType; label: string; value: number; suffix?: string; color: string;
}) {
  const display = useCountUp(value);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-surface p-5 flex items-center gap-4"
    >
      <div className={`rounded-lg p-3 ${color}`}>
        <Icon className="h-5 w-5 text-white" />
      </div>
      <div>
        <p className="text-xs text-text-secondary uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-bold text-text-primary">
          {typeof value === "number" && value % 1 !== 0 ? display.toFixed(1) : Math.round(display)}
          {suffix && <span className="text-sm font-normal text-text-secondary ml-1">{suffix}</span>}
        </p>
      </div>
    </motion.div>
  );
}

export default function KPICards({ summary }: { summary: Summary | null }) {
  if (!summary) return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {[0,1,2,3,4].map(i => <div key={i} className="h-24 rounded-xl bg-surface animate-pulse" />)}
    </div>
  );

  const cards = [
    { icon: TrendingUp, label: "Match Rate", value: summary.match_rate_pct, suffix: "%", color: "bg-success" },
    { icon: Activity, label: "Total Transactions", value: summary.total_records, color: "bg-info" },
    { icon: AlertTriangle, label: "Exceptions", value: summary.unresolved_exception_count, color: "bg-danger" },
    { icon: Clock, label: "Resolved w/ Reasoning", value: summary.resolved_with_reasoning_count, color: "bg-warning" },
    { icon: BarChart3, label: "Avg Confidence", value: summary.average_confidence_score * 100, suffix: "%", color: "bg-accent" },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {cards.map(c => <Card key={c.label} {...c} />)}
    </div>
  );
}
