import { useSyncExternalStore } from "react";

/** Router hash (08-ui-ux.md §2): /#/path?query. */
export interface Location {
  path: string;
  query: URLSearchParams;
}

function read(): Location {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, search = ""] = raw.split("?");
  return { path: path || "/", query: new URLSearchParams(search) };
}

let current = read();
function subscribe(cb: () => void) {
  const onChange = () => {
    current = read();
    cb();
  };
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export function useLocation(): Location {
  return useSyncExternalStore(subscribe, () => current);
}

export function navigate(to: string) {
  window.location.hash = to;
}

/** Cocokkan pola seperti "/streams/:id" dengan path; kembalikan parameter atau null. */
export function match(pattern: string, path: string): Record<string, string> | null {
  const p = pattern.split("/");
  const s = path.split("/");
  if (p.length !== s.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(":")) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}
