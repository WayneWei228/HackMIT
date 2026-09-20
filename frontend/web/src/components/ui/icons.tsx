import type { SVGProps } from "react";

/**
 * Shared icon set, traced from the design comps.
 *
 * Every path is the original geometry - stroke colour is the only thing that
 * changed: the comps hard-coded hex per instance, these inherit `currentColor`
 * so a Tailwind text colour on the parent drives them.
 */

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({
  size = 18,
  viewBox = "0 0 18 18",
  children,
  ...props
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

const S = {
  stroke: "currentColor",
  strokeWidth: 1.25,
} as const;

export function HomeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path
        d="M2.6 7.6L9 2.6l6.4 5v7.1a.9.9 0 0 1-.9.9H3.5a.9.9 0 0 1-.9-.9z"
        {...S}
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function DocIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.6 2.3h7L14.4 6v9.7H3.6z" {...S} strokeLinejoin="round" />
      <path d="M10.6 2.3V6h3.8" {...S} strokeLinejoin="round" />
    </Icon>
  );
}

/** The narrower 14x16 page glyph used inside lists and evidence cards. */
export function PageIcon({
  size = 14,
  strokeWidth = 1.25,
  ...props
}: IconProps) {
  return (
    <svg
      width={size}
      height={(size / 14) * 16}
      viewBox="0 0 14 16"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M2.2 1.6h6.3L11.8 5v9.4H2.2z"
        {...S}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
      <path
        d="M8.5 1.6V5h3.3"
        {...S}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function VendorsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="2.5" y="3.4" width="13" height="11.2" rx="1.6" {...S} />
      <path d="M2.5 7.2h13" {...S} />
      <circle cx="5.6" cy="10.8" r="1" fill="currentColor" />
    </Icon>
  );
}

export function InsightsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="2.5" y="3" width="13" height="12" rx="1.6" {...S} />
      <path
        d="M5.2 11.4l2.4-2.9 2.2 1.9 2.8-3.3"
        {...S}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="9" cy="9" r="2.6" {...S} />
      <circle cx="9" cy="9" r="6.1" {...S} strokeDasharray="2.2 2.4" />
    </Icon>
  );
}

export function SearchIcon({ size = 17, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 17 17" {...props}>
      <circle cx="7.6" cy="7.6" r="5.1" stroke="currentColor" strokeWidth={1.3} />
      <path
        d="M11.4 11.4L14.6 14.6"
        stroke="currentColor"
        strokeWidth={1.3}
        strokeLinecap="round"
      />
    </Icon>
  );
}

export function ChevronDownIcon({
  size = 12,
  strokeWidth = 1.3,
  ...props
}: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 12 12" {...props}>
      <path
        d="M3 4.6L6 7.6l3-3"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function ChevronRightIcon({
  size = 12,
  strokeWidth = 1.3,
  ...props
}: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 12 12" {...props}>
      <path
        d="M4.4 2.6l3 3.4-3 3.4"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function CaretLeftIcon({
  size = 12,
  strokeWidth = 1.3,
  ...props
}: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 12 12" {...props}>
      <path
        d="M7.4 2.2l-3.2 3.8 3.2 3.8"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function CaretRightIcon({
  size = 12,
  strokeWidth = 1.3,
  ...props
}: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 12 12" {...props}>
      <path
        d="M4.6 2.2l3.2 3.8-3.2 3.8"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function PlusIcon({ size = 13, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 13 13" {...props}>
      <path
        d="M6.5 1.6v9.8M1.6 6.5h9.8"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    </Icon>
  );
}

export function CalendarIcon({ size = 15, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 16 16" {...props}>
      <rect
        x="1.8"
        y="2.8"
        width="12.4"
        height="11.4"
        rx="1.6"
        stroke="currentColor"
        strokeWidth={1.15}
      />
      <path
        d="M1.8 6.2h12.4M5.2 1.6v2.4M10.8 1.6v2.4"
        stroke="currentColor"
        strokeWidth={1.15}
        strokeLinecap="round"
      />
    </Icon>
  );
}

export function SortIcon({ size = 9, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 9 12" {...props}>
      <path
        d="M4.5 1.4l2.3 2.6H2.2zM4.5 10.6l2.3-2.6H2.2z"
        fill="currentColor"
      />
    </Icon>
  );
}

export function CheckIcon({ size = 12, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 12 12" {...props}>
      <path
        d="M2.6 6.2l2.3 2.3 4.5-4.8"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function CheckCircleIcon({ size = 14, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 14 14" {...props}>
      <circle cx="7" cy="7" r="6.1" fill="currentColor" />
      <path
        d="M4.2 7.1l1.9 1.9 3.7-4"
        stroke="#FFFFFF"
        strokeWidth={1.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function RefreshIcon({ size = 12, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 12 12" {...props}>
      <path
        d="M10 6a4 4 0 1 1-1.3-2.9"
        stroke="currentColor"
        strokeWidth={1.3}
        strokeLinecap="round"
      />
      <path
        d="M10.2 1.3v2.6H7.6"
        stroke="currentColor"
        strokeWidth={1.3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function MoreIcon({ className = "", ...props }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`select-none leading-none tracking-wider ${className}`}
      {...props}
    >
      •••
    </span>
  );
}

export function MailIcon({ size = 15, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 16 16" {...props}>
      <rect x="1.9" y="3.4" width="12.2" height="9.2" rx="1.6" {...S} />
      <path d="M2.4 4.7l5.1 3.9a0.8 0.8 0 0 0 1 0l5.1-3.9" {...S} strokeLinecap="round" strokeLinejoin="round" />
    </Icon>
  );
}

export function CloseIcon({ size = 14, ...props }: IconProps) {
  return (
    <Icon size={size} viewBox="0 0 14 14" {...props}>
      <path d="M3.2 3.2l7.6 7.6M10.8 3.2l-7.6 7.6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </Icon>
  );
}
