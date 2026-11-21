import type { SVGProps } from "react";

type IconName = "products" | "plans" | "settings" | "plus" | "upload" | "download" | "back" | "arrow" | "check";

const paths: Record<IconName, React.ReactNode> = {
  products: <><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M8 4v16M3 9h18M3 15h18" /></>,
  plans: <><path d="M6 3h9l4 4v14H6z" /><path d="M15 3v5h5M9 12h7M9 16h7" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1a1.7 1.7 0 1 1-2.4 2.4l-.1-.1a1.7 1.7 0 0 0-2.9 1.2v.3a1.7 1.7 0 1 1-3.4 0v-.2A1.7 1.7 0 0 0 7.8 17l-.1.1a1.7 1.7 0 1 1-2.4-2.4l.1-.1a1.7 1.7 0 0 0-1.2-2.9h-.3a1.7 1.7 0 1 1 0-3.4h.2A1.7 1.7 0 0 0 5.3 6l-.1-.1a1.7 1.7 0 1 1 2.4-2.4l.1.1a1.7 1.7 0 0 0 2.9-1.2v-.3a1.7 1.7 0 1 1 3.4 0v.2A1.7 1.7 0 0 0 17 3.5l.1-.1a1.7 1.7 0 1 1 2.4 2.4l-.1.1a1.7 1.7 0 0 0 1.2 2.9h.3a1.7 1.7 0 1 1 0 3.4h-.2a1.7 1.7 0 0 0-1.3 2.8Z" transform="translate(2 2) scale(.83)" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
  upload: <><path d="M12 16V4m0 0L7 9m5-5 5 5" /><path d="M4 15v5h16v-5" /></>,
  download: <><path d="M12 4v12m0 0 5-5m-5 5-5-5" /><path d="M4 19h16" /></>,
  back: <><path d="m14 5-7 7 7 7" /><path d="M7 12h13" /></>,
  arrow: <><path d="M4 12h15" /><path d="m13 6 6 6-6 6" /></>,
  check: <><path d="m5 12 4 4L19 6" /></>,
};

export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
      {paths[name]}
    </svg>
  );
}
