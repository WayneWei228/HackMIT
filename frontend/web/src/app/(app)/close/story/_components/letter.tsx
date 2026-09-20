/**
 * A piece of correspondence, set as the sheet it is.
 *
 * The close's turning points are letters - the question it sent, the answer it
 * got - so they are shown whole, in the flow, rather than summarised.
 */
export function Letter({
  direction,
  party,
  date,
  subject,
  body,
  footnote,
}: {
  direction: "sent" | "received";
  /** Who it went to, or came from. */
  party: string;
  date: string;
  subject: string;
  body: string;
  footnote?: string;
}) {
  return (
    <article className="max-w-[640px] rounded-[3px] border border-line-dark bg-panel px-7 pt-5 pb-6 shadow-[0_1px_0_rgba(29,31,27,0.04),0_10px_24px_-18px_rgba(29,31,27,0.35)]">
      <header className="flex items-baseline justify-between gap-6 border-b border-line pb-3 text-meta text-faint-2">
        <span>
          {direction === "sent" ? "To " : "From "}
          <span className="text-ink-2">{party}</span>
        </span>
        <span className="flex-none">{date}</span>
      </header>
      {subject && (
        <h3 className="font-display mt-4 mb-0 text-xl leading-[1.25] font-normal text-ink-deep">
          {subject}
        </h3>
      )}
      <div className="mt-3 text-sm leading-[1.65] whitespace-pre-line text-ink-2">
        {body}
      </div>
      {footnote && (
        <p className="mt-4 mb-0 border-t border-line pt-3 text-meta text-faint-2">
          {footnote}
        </p>
      )}
    </article>
  );
}

const HEADER = /^(From|To|Date|Subject):\s*(.*)$/i;

/** A line at least this long was cut by the margin, not by its writer. */
const WRAP_MARGIN = 56;

/**
 * A reply as it was filed: mail headers, a blank line, the letter. The headers
 * become the sheet's own; whatever is not a header is the body, untouched.
 */
export function letterFromText(
  text: string,
  fallbackParty: string,
): { party: string; date: string; subject: string; body: string } {
  const lines = text.replace(/\r\n/g, "\n").trim().split("\n");
  const headers: Record<string, string> = {};
  let at = 0;
  while (at < lines.length) {
    const match = HEADER.exec(lines[at]);
    if (!match) break;
    headers[match[1].toLowerCase()] = match[2].trim();
    at += 1;
  }
  const body = lines.slice(at).join("\n").trim();
  return {
    party: (headers.from ?? fallbackParty).replace(/\s*<[^>]*>\s*$/, ""),
    date: headers.date ?? "",
    subject: (headers.subject ?? "").replace(/^RE:\s*/i, ""),
    /* Hard-wrapped plain text: a line that ran to the margin continues on the
       next one, so the two are rejoined; a short line (a list item, a
       signature) ended on purpose and keeps its break. */
    body: body
      .split(/\n{2,}/)
      .map((block) => {
        const out: string[] = [];
        let wrapped = false;
        for (const line of block.split("\n")) {
          if (wrapped && out.length > 0 && !/^\s*[-*\u2022]/.test(line)) {
            out[out.length - 1] += ` ${line.trim()}`;
          } else {
            out.push(line);
          }
          wrapped = line.length >= WRAP_MARGIN;
        }
        return out.join("\n");
      })
      .join("\n\n"),
  };
}
