import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Info, Loader2, RotateCw, Trash2, UploadCloud } from "lucide-react";
import { api, urls, type Report, type UploadResult } from "../api";
import { Button, Card, ErrorNote, LinkButton, Loading, PageHeader } from "../components/ui";
import { useCanProcess } from "../lib/useCanProcess";

const statusStyle: Record<Report["status"], string> = {
  queued: "bg-low-soft text-low",
  processing: "bg-brand-soft text-brand",
  done: "bg-ok-soft text-ok",
  failed: "bg-high-soft text-high",
};

export function Reports() {
  const canProcess = useCanProcess();
  const qc = useQueryClient();
  const reports = useQuery({
    queryKey: ["reports"],
    queryFn: api.reports,
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "queued" || r.status === "processing") ? 2500 : false),
  });

  // When processing finishes, findings and stats change too.
  const busy = reports.data?.some((r) => r.status === "queued" || r.status === "processing");
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) {
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    }
    wasBusy.current = !!busy;
  }, [busy, qc]);

  const [results, setResults] = useState<UploadResult[]>([]);
  const upload = useMutation({
    mutationFn: api.upload,
    onSuccess: (r) => {
      setResults(r);
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["reports"] });
  const reprocess = useMutation({ mutationFn: api.reprocess, onSuccess: refresh });
  const remove = useMutation({
    mutationFn: api.remove,
    onSuccess: () => {
      refresh();
      qc.invalidateQueries({ queryKey: ["findings"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const send = (files: FileList | null) => {
    const pdfs = [...(files ?? [])].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length) upload.mutate(pdfs);
  };

  if (reports.isLoading) return <Loading />;
  if (reports.error) return <ErrorNote error={reports.error} />;

  return (
    <>
      <PageHeader
        title="Reports"
      />

      {canProcess ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); send(e.dataTransfer.files); }}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          role="button"
          tabIndex={0}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
            dragging ? "border-brand bg-brand-soft" : "border-line bg-panel hover:border-brand/50"
          }`}
        >
          {upload.isPending ? <Loader2 className="h-7 w-7 animate-spin text-brand" /> : <UploadCloud className="h-7 w-7 text-brand" />}
          <p className="mt-2 text-sm font-medium text-ink">{upload.isPending ? "Uploading…" : "Drag PDF reports here"}</p>
          <p className="mt-0.5 text-xs text-muted">Text-based PDFs up to 50 MB each. Processing runs in the background, one report at a time.</p>
          {!upload.isPending && (
            <span className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-brand px-3.5 py-2 text-sm font-medium text-white shadow-sm">
              <UploadCloud className="h-4 w-4" aria-hidden /> Choose files
            </span>
          )}
          <input ref={input} type="file" accept="application/pdf" multiple hidden onChange={(e) => { send(e.target.files); e.target.value = ""; }} />
        </div>
      ) : (
        <div className="flex items-start gap-3 rounded-xl border border-line bg-panel px-5 py-4 text-sm text-ink-soft">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden />
          <p>
            These results were prepared in advance with Gemini. To upload and process new reports, add a Gemini API key
            to <code className="rounded bg-canvas px-1 text-xs">backend/.env</code> and restart the API (see README).
          </p>
        </div>
      )}

      {upload.error && <div className="mt-3"><ErrorNote error={upload.error} /></div>}
      {reprocess.error && <p role="alert" className="mt-3 text-sm text-high">{reprocess.error.message}</p>}
      {results.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {results.map((r) => (
            <li key={r.file} className={r.error ? "text-high" : r.duplicate ? "text-medium" : "text-ink-soft"}>
              <span className="font-medium">{r.file}</span>:{" "}
              {r.error ??
                (r.duplicate
                  ? `not added. ${r.reason ?? "Already uploaded"} (${r.report_id}).`
                  : `queued as ${r.report_id}.`)}
              {!r.error && !r.duplicate && <UploadWarning result={r} />}
            </li>
          ))}
        </ul>
      )}

      <Card className="mt-6 overflow-hidden">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="border-b border-line bg-canvas/60 text-left text-xs text-muted">
            <tr>
              <th className="px-4 py-2.5 font-medium">Report</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 text-right font-medium">Pages</th>
              <th className="px-4 py-2.5 text-right font-medium">IT findings</th>
              <th className="px-4 py-2.5 font-medium" title="Bookmarks that pointed to the wrong page and were corrected">Bookmark fixes</th>
              <th className="px-4 py-2.5 font-medium">Model</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {reports.data!.map((r) => (
              <tr key={r.id} className="align-top">
                <td className="px-4 py-3">
                  <p className="font-medium text-ink">{r.fiscal_year}</p>
                  <p className="text-xs text-muted">{r.file_name}</p>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${statusStyle[r.status]}`}>
                    {r.status === "processing" && <Loader2 className="h-3 w-3 animate-spin" />}
                    {r.status}
                  </span>
                  {r.progress && r.status === "processing" && <p className="mt-1 text-xs text-muted">{r.progress}</p>}
                  {r.error && <p className="mt-1 max-w-xs text-xs text-high">{r.error}</p>}
                </td>
                <td className="px-4 py-3 text-right text-ink-soft">{r.page_count}</td>
                <td className="px-4 py-3 text-right font-semibold text-ink">{r.status === "done" ? r.finding_count : "—"}</td>
                <td className="px-4 py-3 text-ink-soft">{r.bookmarks_corrected || "—"}</td>
                <td className="px-4 py-3 text-xs text-muted">{r.model ?? "—"}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1.5">
                    {r.status === "done" && r.finding_count > 0 && (
                      <LinkButton size="sm" variant="ghost" to={`/findings?year=${encodeURIComponent(r.fiscal_year)}`}>Findings</LinkButton>
                    )}
                    <Button size="sm" href={urls.reportPdf(r.id)} title="Open the report PDF in a new tab">
                      <ExternalLink className="h-3.5 w-3.5" /> PDF
                    </Button>
                    <Button
                      size="sm"
                      title={canProcess ? "Re-extract findings (uses Gemini calls)" : "Needs a Gemini API key (see README)"}
                      disabled={!canProcess || r.status === "queued" || r.status === "processing"}
                      onClick={() => window.confirm(`Re-extract ${r.fiscal_year} with Gemini? This makes a few API calls.`) && reprocess.mutate(r.id)}
                    >
                      <RotateCw className="h-3.5 w-3.5" /> Re-run
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      title="Delete report and its findings"
                      onClick={() => window.confirm(`Delete ${r.fiscal_year} and its findings?`) && remove.mutate(r.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Delete
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </Card>
    </>
  );
}

/** Overlap with existing reports never blocks an upload (it may be a corrected
 * edition), but both versions would count towards the dashboard, so say so. */
function UploadWarning({ result }: { result: UploadResult }) {
  const overlap = result.overlaps?.[0];
  const sameYear = (result.same_year ?? []).filter((id) => id !== overlap?.report_id);
  if (!overlap && !sameYear.length) return null;
  return (
    <span className="text-medium">
      {overlap && <> {Math.round(overlap.share * 100)}% of its pages match {overlap.report_id}.</>}
      {sameYear.length > 0 && <> A report for the same year is already loaded ({sameYear.join(", ")}).</>}
      {" "}If this replaces an older version, delete that one so its findings aren't counted twice.
    </span>
  );
}
