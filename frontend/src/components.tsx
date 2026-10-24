import React from "react";
import {
  Cube,
  FileText,
  ChartBar,
  ListChecks,
  BookOpen,
  Database,
  Info,
  ShieldCheck,
} from "@phosphor-icons/react";
import {
  Badge,
  Button as LegacyButton,
  Field as LegacyField,
  Callout,
  Modal as LegacyModal,
  downloadJSON,
} from "./ui.jsx";
export { Badge, Callout, downloadJSON };
export const Button = LegacyButton as React.ComponentType<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: string;
    icon?: any;
  }
>;
export const Field = LegacyField as React.ComponentType<{
  label: string;
  hint?: string;
  children: React.ReactNode;
}>;
export const Modal = LegacyModal as React.ComponentType<{
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
  drawer?: boolean;
  footer?: React.ReactNode;
}>;

export const icons: Record<string, any> = {
  Concept: Cube,
  "Business term": FileText,
  Metric: ChartBar,
  Rule: ListChecks,
  Page: BookOpen,
  table: Database,
  view: Database,
  metric_view: ChartBar,
  catalog: Database,
  schema: Database,
};
export function TypeIcon({ type }: { type: string }) {
  const Icon = icons[type] || Cube;
  return (
    <span
      className={`object-icon icon-${type.toLowerCase().replace(" ", "-")}`}
    >
      <Icon size={20} />
    </span>
  );
}
export function Status({ value }: { value: string }) {
  const tone = [
    "Approved",
    "Verified",
    "sufficient",
    "healthy",
    "permitted",
    "Published",
  ].includes(value)
    ? "teal"
    : [
          "Draft",
          "Needs review",
          "incomplete",
          "stale",
          "Conflict",
          "Unsupported",
          "outage",
          "withheld",
        ].includes(value)
      ? "amber"
      : ["denied", "error", "Failed", "Mismatch", "malformed"].includes(value)
        ? "red"
        : "neutral";
  return <Badge tone={tone}>{value}</Badge>;
}
export function Panel({
  title,
  children,
  action,
  className = "",
}: {
  title?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-title">
          <h3>{title}</h3>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Title({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="screen-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function Tabs({
  items,
  value,
  onChange,
}: {
  items: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <>
      <label className="mobile-section-picker">
        <span>View</span>
        <select
          aria-label="View section"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          {items.map((i) => (
            <option key={i}>{i}</option>
          ))}
        </select>
      </label>
      <nav className="tabs" aria-label="Section tabs">
        {items.map((i) => (
          <button
            key={i}
            aria-current={value === i ? "page" : undefined}
            className={value === i ? "active" : ""}
            onClick={() => onChange(i)}
          >
            {i}
          </button>
        ))}
      </nav>
    </>
  );
}
export function StateNotice({
  title,
  children,
  kind = "empty",
}: {
  title: string;
  children?: React.ReactNode;
  kind?: string;
}) {
  return (
    <div
      className={`state-notice ${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      <Info size={22} />
      <div>
        <h3>{title}</h3>
        <p>{children}</p>
      </div>
    </div>
  );
}
export function Json({ value }: { value: unknown }) {
  return <pre className="code-block">{JSON.stringify(value, null, 2)}</pre>;
}
export function KeyValue({
  items,
}: {
  items: Record<string, React.ReactNode>;
}) {
  return (
    <dl className="key-values">
      {Object.entries(items).map(([k, v]) => (
        <React.Fragment key={k}>
          <dt>{k}</dt>
          <dd>{v || "Not supplied"}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}
export function PermissionSummary() {
  return (
    <Callout icon={ShieldCheck}>
      Metadata only. Domain ownership does not grant native access. This demo
      never queries source records.
    </Callout>
  );
}
export function TextInput({
  label,
  value,
  onChange,
  area = false,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  area?: boolean;
  hint?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      {area ? (
        <textarea
          rows={4}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input value={value} onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}
export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <Field label={label}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option value={o.value} key={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
export const opts = (values: string[]) =>
  values.map((value) => ({ value, label: value }));
