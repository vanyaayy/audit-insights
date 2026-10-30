import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, AlertTriangle, XCircle, ChevronRight, FileText } from "lucide-react";
import type { Severity, Verification } from "../api";
import { severityClass } from "../lib/format";

const focusRing = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-1";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-line bg-panel shadow-[0_1px_2px_rgba(15,27,45,0.04)] ${className}`}>{children}</section>;
}

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}

/** Groups related cards on a page under one heading. */
export function Section({
  id, title, description, action, children,
}: { id?: string; title: string; description?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 pt-10 first:pt-0">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-line pb-2.5">
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${severityClass[severity]}`}>
      {severity}
    </span>
  );
}

const verificationMeta: Record<Verification, { label: string; icon: typeof CheckCircle2; cls: string }> = {
  verified: { label: "Traced to source", icon: CheckCircle2, cls: "text-ok" },
  partial: { label: "Partly verified", icon: AlertTriangle, cls: "text-medium" },
  unverified: { label: "Needs review", icon: XCircle, cls: "text-high" },
};

export function VerificationMark({ value, withLabel = false }: { value: Verification; withLabel?: boolean }) {
  const m = verificationMeta[value];
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${m.cls}`} title={m.label}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {withLabel ? m.label : <span className="sr-only">{m.label}</span>}
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center rounded-md bg-canvas px-2 py-0.5 text-xs text-ink-soft ring-1 ring-inset ring-line">{children}</span>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-serif text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink-soft">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

function buttonClass(variant: Variant, size: Size) {
  const base = `inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50 ${focusRing}`;
  const sizes = { sm: "px-2.5 py-1 text-xs", md: "px-3.5 py-2 text-sm" };
  const variants = {
    primary: "bg-brand text-white shadow-sm hover:bg-brand/90",
    secondary: "bg-panel text-ink shadow-sm ring-1 ring-inset ring-line hover:bg-canvas hover:ring-ink/20",
    ghost: "text-brand hover:bg-brand-soft",
    danger: "bg-panel text-high ring-1 ring-inset ring-high/25 hover:bg-high-soft",
  };
  return `${base} ${sizes[size]} ${variants[variant]}`;
}

export function Button({
  children, onClick, variant = "secondary", size = "md", disabled, href, download, title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: Variant;
  size?: Size;
  disabled?: boolean;
  href?: string;
  download?: boolean;
  title?: string;
}) {
  const cls = buttonClass(variant, size);
  if (href) {
    return <a className={cls} href={href} download={download} title={title} target={download ? undefined : "_blank"} rel="noreferrer">{children}</a>;
  }
  return <button type="button" className={cls} onClick={onClick} disabled={disabled} title={title}>{children}</button>;
}

/** In-app navigation styled as a button. */
export function LinkButton({ to, children, variant = "secondary", size = "md" }: { to: string; children: ReactNode; variant?: Variant; size?: Size }) {
  return <Link to={to} className={buttonClass(variant, size)}>{children}</Link>;
}

/** The trailing "View" affordance on clickable rows, so it's obvious they open something. */
export function ViewCue({ label = "View" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-0.5 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-brand ring-1 ring-inset ring-brand/20 transition group-hover:bg-brand group-hover:text-white">
      {label} <ChevronRight className="h-3.5 w-3.5" aria-hidden />
    </span>
  );
}

/** A citation that opens the finding it refers to. */
export function SourceChip({ label, title, onClick, block = false }: { label: string; title?: string; onClick: () => void; block?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`group items-center gap-1.5 rounded-md border border-line bg-panel px-2 py-1 text-left text-xs text-ink-soft shadow-sm transition hover:border-brand/40 hover:bg-brand-soft hover:text-brand ${block ? "flex w-full" : "inline-flex"} ${focusRing}`}
    >
      <FileText className="h-3.5 w-3.5 shrink-0 text-brand" aria-hidden />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {block && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted group-hover:text-brand" aria-hidden />}
    </button>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div role="status" className="rounded-xl border border-dashed border-line bg-panel px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Loading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading">
      <div className="h-8 w-1/3 animate-pulse rounded-lg bg-line/70" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-line/60" />)}
      </div>
      <div className="h-64 animate-pulse rounded-xl bg-line/50" />
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  return (
    <div role="alert" className="rounded-lg border border-high/30 bg-high-soft px-4 py-3 text-sm text-high">
      {error instanceof Error ? error.message : "Something went wrong"}. Is the API running on port 8000?
    </div>
  );
}

export { focusRing };
