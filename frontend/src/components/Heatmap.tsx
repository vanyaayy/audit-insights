import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { Repeat } from "lucide-react";
import type { Stats } from "../api";
import { shortYear } from "../lib/format";
import { focusRing } from "./ui";

const shade = (n: number, max: number) => (n ? 0.12 + 0.88 * (n / max) : 0);

/** Control domain x report year. Each non-empty cell is a button that opens the
 * filtered findings register; darker means more findings. */
export function Heatmap({ stats }: { stats: Stats }) {
  const years = stats.reports;
  const domains = Object.entries(stats.domains);
  const max = Math.max(1, ...domains.flatMap(([, d]) => Object.values(d.by_year)));

  // With many years the columns scroll; start at the most recent ones.
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [years.length]);

  return (
    <div>
      <div ref={scroller} className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1.5 text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 min-w-48 bg-panel px-2 text-left text-xs font-medium text-muted">Control area</th>
              {years.map((y) => (
                <th key={y} className="min-w-14 text-center text-xs font-medium whitespace-nowrap text-muted">{shortYear(y)}</th>
              ))}
              <th className="sticky right-0 z-10 min-w-16 bg-panel text-center text-xs font-medium whitespace-nowrap text-muted">All years</th>
            </tr>
          </thead>
          <tbody>
            {domains.map(([name, d]) => (
              <tr key={name}>
                <th scope="row" className="sticky left-0 z-10 min-w-48 bg-panel px-2 py-1 text-left font-normal text-ink-soft">
                  <span className="inline-flex items-center gap-1.5">
                    {name}
                    {d.years_present >= 2 && (
                      <Repeat className="h-3.5 w-3.5 shrink-0 text-high" aria-label="Recurring in 2 or more years" />
                    )}
                  </span>
                </th>
                {years.map((y) => {
                  const n = d.by_year[y] ?? 0;
                  const a = shade(n, max);
                  return (
                    <td key={y} className="p-0">
                      {n ? (
                        <Link
                          to={`/findings?domain=${encodeURIComponent(name)}&year=${encodeURIComponent(y)}`}
                          className={`block rounded-md border border-brand/20 py-2 text-center font-semibold shadow-sm transition hover:-translate-y-px hover:shadow-md hover:ring-2 hover:ring-brand/50 ${focusRing}`}
                          style={{ backgroundColor: `rgba(18, 69, 107, ${a})`, color: a > 0.5 ? "white" : "#12456b" }}
                          aria-label={`${n} ${name} findings in ${y}. Open.`}
                        >
                          {n}
                        </Link>
                      ) : (
                        <span className="block rounded-md py-2 text-center text-line" aria-label="None">–</span>
                      )}
                    </td>
                  );
                })}
                <td className="sticky right-0 z-10 bg-panel p-0 pl-1.5">
                  <Link
                    to={`/findings?domain=${encodeURIComponent(name)}`}
                    className={`block rounded-md border border-line bg-panel py-2 text-center font-semibold text-ink shadow-sm transition hover:border-brand/40 hover:bg-brand-soft hover:text-brand ${focusRing}`}
                    aria-label={`All ${d.total} ${name} findings. Open.`}
                  >
                    {d.total}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-2 pt-3 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          Fewer
          {[1, 2, 3, 4].map((n) => (
            <span key={n} className="h-3 w-5 rounded-sm" style={{ backgroundColor: `rgba(18, 69, 107, ${shade(n, 4)})` }} />
          ))}
          More
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Repeat className="h-3.5 w-3.5 text-high" aria-hidden /> Recurring in 2+ years
        </span>
      </div>
    </div>
  );
}
