import React, { useEffect, useLayoutEffect, useRef, useId } from "react";
import {
  X,
  ArrowUpRight,
  CheckCircle,
  Circle,
  WarningCircle,
  CaretRight,
} from "@phosphor-icons/react";

export function Badge({
  children,
  tone = "neutral",
  dot = false,
  className = "",
}) {
  return (
    <span className={`badge badge-${tone} ${className}`}>
      {dot && <span className="status-dot" />}
      {children}
    </span>
  );
}
export function Button({
  children = null,
  variant = "secondary",
  icon: Icon = null,
  className = "",
  ...props
}) {
  return (
    <button className={`button button-${variant} ${className}`} {...props}>
      {Icon && <Icon size={17} />}
      {children}
    </button>
  );
}
export function IconButton({ label, children, className = "", ...props }) {
  return (
    <button
      className={`icon-button ${className}`}
      aria-label={label}
      title={label}
      {...props}
    >
      {children}
    </button>
  );
}
export function SectionTitle({ children, action }) {
  return (
    <div className="section-heading">
      <h3>{children}</h3>
      {action}
    </div>
  );
}
export function Field({ label, hint = null, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}
export function EmptyState({
  icon: Icon = Circle,
  title,
  description,
  action,
}) {
  return (
    <div className="empty-state">
      <Icon size={32} weight="light" />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function Callout({ children, tone = "teal", icon: Icon = CheckCircle }) {
  return (
    <div className={`callout callout-${tone}`}>
      <Icon size={20} />
      <div>{children}</div>
    </div>
  );
}
export function Toggle({ checked, onChange, label, description }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className="toggle-row"
      onClick={() => onChange(!checked)}
    >
      <span className={`switch ${checked ? "is-on" : ""}`}>
        <span />
      </span>
      <span>
        <strong>{label}</strong>
        {description && <small>{description}</small>}
      </span>
    </button>
  );
}
export function Breadcrumb({ items }) {
  return (
    <div className="breadcrumb">
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <CaretRight size={12} />}
          {typeof item === "string" ? (
            <span>{item}</span>
          ) : (
            <button onClick={item.onClick}>{item.label}</button>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}
export function Modal({
  title,
  description = null,
  onClose,
  children,
  wide = false,
  footer = null,
  drawer = false,
}) {
  const titleId = useId();
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useLayoutEffect(() => {
    const prev = document.activeElement;
    const el = ref.current;
    const focus = () => {
      const target =
        el?.querySelector("input,textarea,select") ||
        el?.querySelector("button");
      target?.focus({ preventScroll: true });
    };
    focus();
    const onKey = (e) => {
      if ([...document.querySelectorAll("[role=dialog]")].at(-1) !== el) return;
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab") {
        const f = [
          ...el.querySelectorAll(
            'button,input,select,textarea,a[href],[tabindex="0"]',
          ),
        ].filter((x) => !x.disabled && x.getClientRects().length);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) {
          e.preventDefault();
          f.at(-1).focus();
        } else if (!e.shiftKey && document.activeElement === f.at(-1)) {
          e.preventDefault();
          f[0].focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, []);
  return (
    <div
      className={`modal-backdrop ${drawer ? "drawer-backdrop" : ""}`}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <section
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`modal ${wide ? "modal-wide" : ""} ${drawer ? "modal-drawer" : ""}`}
      >
        <header className="modal-header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <IconButton label="Close dialog" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </header>
        <div className="modal-content">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </section>
    </div>
  );
}
export function downloadJSON(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
