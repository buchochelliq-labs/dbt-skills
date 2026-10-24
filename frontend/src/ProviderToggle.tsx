import React from "react";
import type { Provider } from "./contracts";
import { Button } from "./components";

export function ProviderToggle({ provider, onToggle }: {
  provider: Provider;
  onToggle: () => void;
}) {
  if (provider.retired) return <span>Removed from server configuration</span>;
  return <Button onClick={onToggle}>{provider.enabled ? "Pause" : "Enable"}</Button>;
}
