"use client";

import { useCallback, useEffect, useState } from "react";

import { API_BASE_URL, getJson, HttpError } from "./api";

/**
 * One screen's data, and nothing else.
 *
 * There is no mock floor and no demo fallback. Everything the product shows
 * comes from the backend, so a screen is in exactly one of four states: it is
 * waiting, it has data, the backend answered with nothing to show, or the
 * backend could not be reached. Each of those has a designed rendering; none
 * of them is "here is somebody else's data instead".
 */
export type LiveStatus = "loading" | "ready" | "empty" | "error";

export type LiveResult<T> = {
  status: LiveStatus;
  /** Only ever non-null when `status` is "ready". */
  data: T | null;
  /** Why the fetch failed, for the error state. */
  error: string | null;
  /** The HTTP code, when the backend answered but refused. 404 = no such thing. */
  httpStatus: number | null;
  /** The URL that failed, so the error state can name it. */
  url: string | null;
  /** Fetch again - what the error state's retry button calls. */
  retry: () => void;
};

export type LiveOptions<T> = {
  /**
   * Whether an answer counts as nothing to show - an empty case list, a
   * screen whose panels would all be blank. Must be a stable reference.
   */
  isEmpty?: (data: T) => boolean;
};

function describe(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

type Answer<T> =
  | { path: string; token: number; data: T }
  | { path: string; token: number; error: string; httpStatus: number | null };

/**
 * Fetch one screen's data.
 *
 * A `null` path means there is nothing to fetch - no case selected, no month
 * chosen - which is "empty", not "loading": the screen should say what it
 * needs rather than spin forever.
 */
export function useLiveData<T extends object>(
  path: string | null,
  options?: LiveOptions<T>,
): LiveResult<T> {
  const isEmpty = options?.isEmpty;
  const [token, setToken] = useState(0);
  const [answer, setAnswer] = useState<Answer<T> | null>(null);

  useEffect(() => {
    if (!path) return;

    const controller = new AbortController();
    let cancelled = false;

    getJson<T>(path, controller.signal)
      .then((data) => {
        if (cancelled) return;
        setAnswer({ path, token, data });
      })
      .catch((error: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setAnswer({
          path,
          token,
          error: describe(error),
          httpStatus: error instanceof HttpError ? error.status : null,
        });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [path, token]);

  const retry = useCallback(() => setToken((value) => value + 1), []);

  const url = path ? `${API_BASE_URL}${path}` : null;

  if (!path) {
    return {
      status: "empty",
      data: null,
      error: null,
      httpStatus: null,
      url: null,
      retry,
    };
  }

  // An answer for a path we have since navigated away from is not an answer.
  const current =
    answer && answer.path === path && answer.token === token ? answer : null;

  if (!current) {
    return {
      status: "loading",
      data: null,
      error: null,
      httpStatus: null,
      url,
      retry,
    };
  }
  if ("error" in current) {
    /* A 404 is the backend answering "no such case" - that is an empty
       screen, not a broken one. */
    if (current.httpStatus === 404) {
      return {
        status: "empty",
        data: null,
        error: current.error,
        httpStatus: 404,
        url,
        retry,
      };
    }
    return {
      status: "error",
      data: null,
      error: current.error,
      httpStatus: current.httpStatus,
      url,
      retry,
    };
  }
  if (isEmpty && isEmpty(current.data)) {
    return {
      status: "empty",
      data: null,
      error: null,
      httpStatus: null,
      url,
      retry,
    };
  }
  return {
    status: "ready",
    data: current.data,
    error: null,
    httpStatus: null,
    url,
    retry,
  };
}
