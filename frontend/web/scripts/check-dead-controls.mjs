#!/usr/bin/env node
/**
 * Fail the build if the UI offers a control that does nothing.
 *
 * The product owner pointed at an "Approve and post journal" button and said
 * "I don't have this feature". That is the whole rule: a button, a link or a
 * menu that leads nowhere is a lie about what the product can do, and it is
 * a lie that costs someone their trust the first time they press it.
 *
 * So every `<button>`, `<Button>` and `<a>`/`<Link>` in the app must be able
 * to do something. A control qualifies if it carries any of:
 *   - `onClick` / `onMouseDown` / `onPointerDown` / `onKeyDown` / `onChange`
 *   - `href` (links) or `type="submit"` (forms)
 *   - `disabled` or `aria-disabled` (honestly unavailable, not fake)
 *   - `{...props}` or `{...rest}` (a primitive forwarding a caller's handler)
 * A component that only *defines* a primitive is exempt by the last rule.
 *
 * Run with `npm run check:dead-controls`; part of `npm run verify`.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SRC = join(ROOT, "src");

/** Anything here means the control can act. */
const LIVE = [
  /\bon[A-Z]\w*\s*=/, // onClick, onChange, onMouseDown, ...
  /\bhref\s*=/,
  /\btype\s*=\s*["'{]?submit/,
  /\bdisabled\b/,
  /\baria-disabled\s*=/,
  /\{\s*\.\.\.\w+\s*\}/, // a primitive forwarding the caller's props
  /\basChild\b/,
];

const OPENERS = /<(button|Button|a|Link)(\s|>|$)/;

/** Collect a JSX opening tag from `<tag` to its closing `>`, tracking braces. */
function readTag(source, start) {
  let depth = 0;
  let quote = "";
  for (let i = start; i < source.length; i += 1) {
    const ch = source[i];
    if (quote) {
      if (ch === "\\") i += 1;
      else if (ch === quote) quote = "";
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      continue;
    }
    if (ch === "{") depth += 1;
    else if (ch === "}") depth -= 1;
    else if (ch === ">" && depth === 0) return source.slice(start, i + 1);
  }
  return source.slice(start);
}

/**
 * Blank out comments, keeping length and line numbers.
 *
 * Without this the scanner reads prose about a `<button>` as a `<button>` -
 * the port's comments discuss the markup they explain.
 */
function stripComments(source) {
  const out = source.split("");
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
      } else if (two === "//") {
        state = "line";
        out[i] = " ";
        out[i + 1] = " ";
        i += 2;
        continue;
      } else if (two === "/*") {
        state = "block";
        out[i] = " ";
        out[i + 1] = " ";
        i += 2;
        continue;
      }
      i += 1;
      continue;
    }
    if (state === "string") {
      if (ch === "\\") i += 1;
      else if (ch === quote) state = "code";
      i += 1;
      continue;
    }
    if (state === "line") {
      if (ch === "\n") state = "code";
      else out[i] = " ";
      i += 1;
      continue;
    }
    if (two === "*/") {
      out[i] = " ";
      out[i + 1] = " ";
      state = "code";
      i += 2;
      continue;
    }
    if (ch !== "\n") out[i] = " ";
    i += 1;
  }
  return out.join("");
}

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      yield* walk(full);
      continue;
    }
    if (entry.endsWith(".tsx")) yield full;
  }
}

const findings = [];

for (const file of walk(SRC)) {
  const raw = readFileSync(file, "utf8");
  const source = stripComments(raw);
  for (let i = 0; i < source.length; i += 1) {
    if (source[i] !== "<") continue;
    const rest = source.slice(i, i + 12);
    const match = OPENERS.exec(rest);
    if (!match || match.index !== 0) continue;

    const tag = readTag(source, i);
    if (tag.startsWith("</")) continue;
    if (LIVE.some((re) => re.test(tag))) continue;

    findings.push({
      file,
      line: source.slice(0, i).split("\n").length,
      tag: tag.replace(/\s+/g, " ").slice(0, 110),
    });
  }
}

if (findings.length === 0) {
  console.log("check:dead-controls - clean, every control can act");
  process.exit(0);
}

console.error(
  `check:dead-controls - ${findings.length} control(s) that lead nowhere.\n` +
    "Wire it, mark it disabled, or remove it - the UI must not offer what the\n" +
    "backend cannot do.\n",
);
for (const f of findings) {
  console.error(`  ${relative(ROOT, f.file)}:${f.line}\n    ${f.tag}`);
}
process.exit(1);
