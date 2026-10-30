import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/** True when the API has a Gemini key, so uploads, re-runs and regeneration can run.
 * Without one the app shows the results prepared in advance and those actions are off.
 * Only an explicit "no key" from the server turns them off: if the check itself
 * fails (e.g. an older server), the actions stay available and report their own errors. */
export function useCanProcess(): boolean {
  const { data } = useQuery({ queryKey: ["status"], queryFn: api.status, staleTime: Infinity, retry: false });
  return data ? data.llm_configured : true;
}
