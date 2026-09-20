#!/usr/bin/env node
/**
 * Fail the build if demo content creeps back into the UI.
 *
 * The product holds no content of its own: every name, figure and sentence on
 * screen comes from the close API. That is easy to state and easy to erode -
 * one hardcoded vendor name in a placeholder, one "$1,400" in a width probe,
 * and a screen is quietly lying about somebody's books again.
 *
 * So the rule is mechanical. These literals were the comps' fixture; none of
 * them may appear in a string or an identifier anywhere under `src/`.
 * Comments may discuss them - the history of this port is worth keeping - so
 * comments are stripped before the search.
 *
 * Run with `npm run check:no-mock`; it runs as part of `npm run verify`.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SRC = join(ROOT, "src");

/** The comps' fixture, in the forms it would come back as. */
const BANNED = [
  "Mintlify",
  "OpenAI",
  "ASUS",
  "Notability",
  "Taylor Smith",
  "1,400",
  "1,200",
  "18,600",
  "December 2026",
  "VND-0412",
  "V001",
];

/**
 * "Meta" is a real word (React `React.memo`, `metadata`, `meta` props), so it
 * is only banned as a standalone vendor-shaped token.
 */
const BANNED_PATTERNS = [
  { label: "Meta (as a vendor name)", re: /["'`]Meta["'`]/ },
  { label: "a hardcoded $ amount", re: /["'`]\$\d[\d,]*(\.\d+)?["'`]/ },
];

const EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".css"]);

/** Strip `//`, `/* *\/` and JSX `{/* *\/}` comments, keeping line numbers. */
function stripComments(source) {
  let out = "";
  let i = 0;
  let state = "code";
  let quote = "";
  while (i < source.length) {
    const two = source.slice(i, i + 2);
    const ch = source[i];
    if (state === "code") {
      if (ch === '"' || ch === "'" || ch === "`") {
        state = "string";
        quote = ch;
        out += ch;
        i += 1;
        continue;
      }
      if (two === "//") {
        state = "line";
        i += 2;
        continue;
      }
      if (two === "/*") {
        state = "block";
        i += 2;
        continue;
      }
      out += ch;
      i += 1;
      continue;
    }
    if (state === "string") {
      if (ch === "\\") {
        out += source.slice(i, i + 2);
        i += 2;
        continue;
      }
      if (ch === quote) state = "code";
      out += ch;
      i += 1;
      continue;
    }
    if (state === "line") {
      if (ch === "\n") {
        state = "code";
        out += ch;
      }
      i += 1;
      continue;
    }
    // block
    if (two === "*/") {
      state = "code";
      i += 2;
      continue;
    }
    if (ch === "\n") out += ch;
    i += 1;
  }
  return out;
}

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      yield* walk(full);
      continue;
    }
    const dot = entry.lastIndexOf(".");
    if (dot < 0 || !EXTENSIONS.has(entry.slice(dot))) continue;
    yield full;
  }
}

const findings = [];

for (const file of walk(SRC)) {
  const source = readFileSync(file, "utf8");
  const code = stripComments(source);
  const lines = code.split("\n");
  lines.forEach((line, index) => {
    for (const needle of BANNED) {
      if (line.includes(needle)) {
        findings.push({ file, line: index + 1, what: needle, text: line.trim() });
      }
    }
    for (const { label, re } of BANNED_PATTERNS) {
      if (re.test(line)) {
        findings.push({ file, line: index + 1, what: label, text: line.trim() });
      }
    }
  });
}

if (findings.length === 0) {
  console.log("check:no-mock - clean, no demo content under src/");
  process.exit(0);
}

console.error(
  `check:no-mock - ${findings.length} piece(s) of demo content under src/.\n` +
    "Everything on screen must come from the close API; see src/lib/use-live-data.ts.\n",
);
for (const finding of findings) {
  console.error(
    `  ${relative(ROOT, finding.file)}:${finding.line}  ${finding.what}\n` +
      `    ${finding.text}`,
  );
}
process.exit(1);
