import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";

export type ApiState<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "success"; data: T };

/** Runs `load` on mount (and on `reload`), aborting in-flight requests on unmount. */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>): ApiState<T> & {
  reload: () => void;
} {
  const [state, setState] = useState<ApiState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  // State starts as "loading"; reloading resets it here rather than inside the effect.
  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .then((data) => setState({ status: "success", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          error:
            error instanceof ApiError
              ? error
              : new ApiError("UNEXPECTED", "Something went wrong.", null, null),
        });
      });
    return () => controller.abort();
  }, [load, attempt]);

  return { ...state, reload };
}
