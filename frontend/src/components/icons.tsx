import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 16, ...rest }: IconProps): SVGProps<SVGSVGElement> {
  return {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    focusable: false,
    ...rest,
  };
}

export const SpinnerIcon = (p: IconProps) => (
  <svg {...base(p)} className={`spinner ${p.className ?? ""}`}>
    <circle cx="8" cy="8" r="6" opacity="0.25" />
    <path d="M14 8a6 6 0 0 0-6-6" />
  </svg>
);

export const CheckIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M3.2 8.4l3 3 6.6-6.8" />
  </svg>
);

export const CrossIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </svg>
);

/** Stopped without a reported outcome. */
export const StopIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="4" y="4" width="8" height="8" rx="1.5" />
  </svg>
);

export const QueuedIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="8" cy="8" r="5.2" strokeDasharray="2.4 2.2" />
  </svg>
);

export const WarningIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M8 2.2l6.2 11H1.8z" />
    <path d="M8 6.6v3M8 11.6v.1" />
  </svg>
);

export const OfflineIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M2 2l12 12" />
    <path d="M5.4 7.4A5 5 0 0 1 8 6.8M1.8 5.2a9 9 0 0 1 3-1.8M10.6 4a9 9 0 0 1 3.6 1.2M8 12.6h.01" />
  </svg>
);

export const ExternalIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M9.5 2.5h4v4M13.5 2.5L7.5 8.5M12 9.5v3.2a.8.8 0 0 1-.8.8H3.3a.8.8 0 0 1-.8-.8V4.8a.8.8 0 0 1 .8-.8h3.2" />
  </svg>
);

export const DocumentIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M9.5 1.8H4.3a.8.8 0 0 0-.8.8v10.8a.8.8 0 0 0 .8.8h7.4a.8.8 0 0 0 .8-.8V4.8z" />
    <path d="M9.5 1.8v3h3M5.8 8h4.4M5.8 10.6h4.4" />
  </svg>
);

export const CopyIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="5.2" y="5.2" width="8.6" height="8.6" rx="1.2" />
    <path d="M10.8 5.2V3a.8.8 0 0 0-.8-.8H3a.8.8 0 0 0-.8.8v7a.8.8 0 0 0 .8.8h2.2" />
  </svg>
);

export const ChevronIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4.5 6.2L8 9.8l3.5-3.6" />
  </svg>
);
