import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** The open finding lives in the URL (?finding=id), so any page can open the
 * drawer and the link can be shared or bookmarked. */
export function useFindingParam() {
  const [params, setParams] = useSearchParams();
  const findingId = params.get("finding");

  const open = useCallback(
    (id: string) =>
      setParams((p) => {
        const next = new URLSearchParams(p);
        next.set("finding", id);
        return next;
      }),
    [setParams],
  );

  const close = useCallback(
    () =>
      setParams((p) => {
        const next = new URLSearchParams(p);
        next.delete("finding");
        return next;
      }),
    [setParams],
  );

  return { findingId, open, close };
}
