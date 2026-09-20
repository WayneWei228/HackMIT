import { Fragment } from "react";

import { cn } from "@/lib/cn";
import {
  AGREEMENT_CLAUSE,
  AP_ROWS,
  EMAIL_THREAD,
  GL_ROWS,
  INVOICE,
  ORDER_FORM,
  PRIOR_CLOSE,
  SLACK_THREAD,
  USAGE_BARS,
  VENDOR_ADDRESS,
  VENDOR_FIELDS,
  VENDOR_TAX_ID,
  type FieldRow,
  type LedgerRow,
  type SourceId,
} from "../_data";

/**
 * The ten document previews.
 *
 * Each card is a miniature of the real artifact rather than a generic tile, so
 * the bodies share only a handful of primitives - a serif title, a hairline
 * rule, a label/value grid and the grey bars that stand in for body copy.
 */

/* -------------------------------------------------------------------------- */
/* Shared card pieces                                                          */
/* -------------------------------------------------------------------------- */

function CardTitle({
  children,
  size = "lg",
}: {
  children: React.ReactNode;
  size?: "lg" | "md";
}) {
  return (
    <div
      className={cn(
        "font-display leading-[1.1] text-ink-deep",
        size === "lg" ? "text-xl" : "text-lg",
      )}
    >
      {children}
    </div>
  );
}

function CardKicker({ children }: { children: React.ReactNode }) {
  return <div className="mt-[5px] text-pico text-muted-6">{children}</div>;
}

function CardRule({ className }: { className?: string }) {
  return <div className={cn("h-px bg-[#EAEAE3]", className)} />;
}

/** The grey bars that stand in for unrendered body copy. */
function BodyBar({ className }: { className?: string }) {
  return <div className={cn("h-[5px] rounded-xs bg-wash-cool", className)} />;
}

/** `DATE / DESCRIPTION / AMOUNT` table shared by the AP and GL cards. */
function LedgerTable({
  descriptionLabel,
  rows,
}: {
  descriptionLabel: string;
  rows: readonly LedgerRow[];
}) {
  return (
    <>
      <div className="mt-3.5 grid grid-cols-[52px_1fr_auto] gap-x-1.5 border-b border-[#EAEAE3] pb-[5px] text-[7.5px] tracking-[0.08em] text-ghost">
        <div>DATE</div>
        <div>{descriptionLabel}</div>
        <div className="text-right">AMOUNT</div>
      </div>
      <div className="mt-2 grid grid-cols-[52px_1fr_auto] gap-x-1.5 gap-y-2 text-nano text-ink-3 tabular-nums">
        {rows.map((row) => (
          <Fragment key={row.date}>
            <div>{row.date}</div>
            <div>{row.description}</div>
            <div className="text-right">{row.amount}</div>
          </Fragment>
        ))}
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Card bodies                                                                 */
/* -------------------------------------------------------------------------- */

function AgreementCard() {
  return (
    <>
      <CardTitle>{AGREEMENT_CLAUSE.vendor}</CardTitle>
      <CardKicker>{AGREEMENT_CLAUSE.documentName}</CardKicker>
      <CardRule className="my-[11px]" />
      <div className="text-pico font-semibold text-[#2D302A]">
        {AGREEMENT_CLAUSE.section}
      </div>
      <div className="mt-[9px] flex gap-[7px]">
        <div className="flex-none text-nano text-ghost tabular-nums">
          {AGREEMENT_CLAUSE.number}
        </div>
        <div className="text-nano leading-[1.7] text-pretty text-ink-3">
          {AGREEMENT_CLAUSE.body}
        </div>
      </div>
    </>
  );
}

function ApCard() {
  return (
    <>
      <CardTitle>Accounts Payable</CardTitle>
      <CardKicker>Vendor History</CardKicker>
      <LedgerTable descriptionLabel="DESCRIPTION" rows={AP_ROWS} />
    </>
  );
}

function PriorCloseCard() {
  return (
    <>
      <CardTitle>{PRIOR_CLOSE.title}</CardTitle>
      <CardKicker>{PRIOR_CLOSE.kicker}</CardKicker>
      <div className="mt-3.5 grid grid-cols-[38px_1fr] gap-1.5 text-nano text-ink-3">
        {PRIOR_CLOSE.fields.map((field) => (
          <Fragment key={field.label}>
            <div className="text-ghost">{field.label}</div>
            <div>{field.value}</div>
          </Fragment>
        ))}
      </div>
      <div className="mt-3 text-nano leading-[1.75] text-pretty text-ink-3">
        {PRIOR_CLOSE.body}
      </div>
    </>
  );
}

function VendorMasterCard() {
  return (
    <>
      <CardTitle>Vendor Master</CardTitle>
      <div className="mt-1.5 text-[8px] tracking-caps text-ghost">
        VENDOR RECORD
      </div>
      <div className="mt-3.5 grid grid-cols-[1fr_auto] gap-x-2 gap-y-[9px] text-nano text-ink-3">
        {VENDOR_FIELDS.map((field) => (
          <Fragment key={field.label}>
            <div className="text-ghost">{field.label}</div>
            <div className="text-right">{field.value}</div>
          </Fragment>
        ))}
        <div className="text-ghost">{VENDOR_ADDRESS.label}</div>
        <div className="text-right leading-[1.5]">
          {VENDOR_ADDRESS.lines.map((line, i) => (
            <Fragment key={line}>
              {i > 0 && <br />}
              {line}
            </Fragment>
          ))}
        </div>
        <div className="text-ghost">{VENDOR_TAX_ID.label}</div>
        <div className="text-right">{VENDOR_TAX_ID.value}</div>
      </div>
    </>
  );
}

function GeneralLedgerCard() {
  return (
    <>
      <CardTitle>General Ledger</CardTitle>
      <CardKicker>Account Activity</CardKicker>
      <LedgerTable descriptionLabel="JE / DESCRIPTION" rows={GL_ROWS} />
    </>
  );
}

function FieldGrid({ fields }: { fields: readonly FieldRow[] }) {
  return (
    <div className="mt-4 grid grid-cols-[1fr_auto] gap-x-2 gap-y-2.5 text-nano text-ink-3">
      {fields.map((field) => (
        <Fragment key={field.label}>
          <div className="text-ghost">{field.label}</div>
          <div className="text-right">{field.value}</div>
        </Fragment>
      ))}
    </div>
  );
}

function InvoiceCard() {
  return (
    <>
      <CardTitle size="md">{INVOICE.title}</CardTitle>
      <CardKicker>{INVOICE.kicker}</CardKicker>
      <FieldGrid fields={INVOICE.fields} />
      <CardRule className="mt-3.5 mb-3" />
      <div className="flex items-baseline justify-between text-pico font-semibold text-ink">
        <div>{INVOICE.totalLabel}</div>
        <div className="tabular-nums">{INVOICE.totalValue}</div>
      </div>
      <BodyBar className="mt-[22px]" />
      <BodyBar className="mt-[7px] w-[68%]" />
    </>
  );
}

function OrderFormCard() {
  return (
    <>
      <CardTitle>{ORDER_FORM.title}</CardTitle>
      <CardKicker>{ORDER_FORM.kicker}</CardKicker>
      <FieldGrid fields={ORDER_FORM.fields} />
      <BodyBar className="mt-[26px]" />
      <BodyBar className="mt-[7px]" />
      <BodyBar className="mt-[7px] w-[52%]" />
    </>
  );
}

function EmailCard() {
  return (
    <>
      <CardTitle size="md">{EMAIL_THREAD.subject}</CardTitle>
      <div className="mt-3.5 grid grid-cols-[34px_1fr] gap-1.5 text-[8px] text-ink-3">
        {EMAIL_THREAD.fields.map((field) => (
          <Fragment key={field.label}>
            <div className="text-ghost">{field.label}</div>
            <div>{field.value}</div>
          </Fragment>
        ))}
      </div>
      <div className="mt-3.5 text-nano leading-[1.75] text-pretty text-ink-3">
        {EMAIL_THREAD.body.map((line, i) => (
          <Fragment key={line}>
            {i > 0 && <br />}
            {line}
          </Fragment>
        ))}
      </div>
    </>
  );
}

function SlackCard() {
  return (
    <>
      <CardTitle size="md">{SLACK_THREAD.title}</CardTitle>
      <CardKicker>{SLACK_THREAD.kicker}</CardKicker>
      <div className="mt-[15px] flex flex-col gap-[11px]">
        {SLACK_THREAD.messages.map((message) => (
          <div key={`${message.author}-${message.at}-${message.body}`}>
            <div className="flex items-baseline gap-[7px]">
              <span className="text-nano font-semibold text-[#2D302A]">
                {message.author}
              </span>
              <span className="text-[8px] text-ghost tabular-nums">
                {message.at}
              </span>
            </div>
            <div className="mt-[3px] text-nano leading-[1.7] text-ink-3">
              {message.body}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function UsageCard() {
  const tallest = Math.max(...USAGE_BARS);
  return (
    <>
      <CardTitle>Usage Report</CardTitle>
      <CardKicker>Mintlify</CardKicker>
      <div className="mt-5 flex h-[62px] items-end gap-[5px]">
        {USAGE_BARS.map((height, i) => (
          <div
            key={`${i}-${height}`}
            style={{ height: `${height}%` }}
            className={cn(
              "flex-1 rounded-[1px]",
              height === tallest ? "bg-[#E4E4DC]" : "bg-hover-alt",
            )}
          />
        ))}
      </div>
      <BodyBar className="mt-5" />
      <BodyBar className="mt-[7px]" />
      <BodyBar className="mt-[7px] w-[58%]" />
    </>
  );
}

export const SOURCE_CARD_BODIES: Record<SourceId, () => React.ReactElement> = {
  agreement: AgreementCard,
  ap: ApCard,
  prior: PriorCloseCard,
  vendor: VendorMasterCard,
  gl: GeneralLedgerCard,
  invoice: InvoiceCard,
  po: OrderFormCard,
  email: EmailCard,
  slack: SlackCard,
  usage: UsageCard,
};
