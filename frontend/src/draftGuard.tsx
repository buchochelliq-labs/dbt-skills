import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { Modal, Button } from "./components";
type Entry = { dirty: boolean; label: string; onDiscard?: () => void };
const Context = createContext<{
  entries: Map<symbol, Entry>;
  attempt: (action: () => void) => void;
}>(null!);
export function DraftGuardProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const entries = useRef(new Map<symbol, Entry>()).current;
  const [pending, setPending] = useState<(() => void) | null>(null);
  const attempt = (action: () => void) => {
    if ([...entries.values()].some((e) => e.dirty)) setPending(() => action);
    else action();
  };
  useEffect(() => {
    const listener = (e: BeforeUnloadEvent) => {
      if ([...entries.values()].some((x) => x.dirty)) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", listener);
    return () => window.removeEventListener("beforeunload", listener);
  }, [entries]);
  return (
    <Context.Provider value={{ entries, attempt }}>
      {children}
      {pending && (
        <Modal
          title="Discard unsaved changes?"
          onClose={() => setPending(null)}
        >
          <p>Your unsaved edits will be lost.</p>
          <ul>
            {[...entries.values()]
              .filter((e) => e.dirty)
              .map((e, i) => (
                <li key={i}>{e.label}</li>
              ))}
          </ul>
          <div className="inline">
            <Button onClick={() => setPending(null)}>Keep editing</Button>
            <Button
              variant="primary"
              onClick={() => {
                const action = pending;
                setPending(null);
                for (const e of entries.values()) {
                  if (e.dirty) e.onDiscard?.();
                  e.dirty = false;
                }
                action();
              }}
            >
              Discard and continue
            </Button>
          </div>
        </Modal>
      )}
    </Context.Provider>
  );
}
export function useNavigationGuard() {
  return useContext(Context).attempt;
}
export function useDraftGuard(
  dirty: boolean,
  label: string,
  onDiscard?: () => void,
) {
  const context = useContext(Context),
    id = useRef(Symbol()).current;
  context.entries.set(id, { dirty, label, onDiscard });
  useEffect(
    () => () => {
      context.entries.delete(id);
    },
    [context.entries, id],
  );
  return {
    attempt: context.attempt,
    markClean: () => {
      const e = context.entries.get(id);
      if (e) e.dirty = false;
    },
  };
}
