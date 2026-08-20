import type { SVGProps } from "react";

export type IconName = "home" | "catalog" | "create" | "history" | "profile" | "image" | "video" | "music" | "wallet" | "close" | "chevron" | "heart" | "comment" | "share" | "upload" | "spark" | "settings";

const paths: Record<IconName, React.ReactNode> = {
  home: <><path d="M3.5 10.6 12 3.7l8.5 6.9"/><path d="M5.5 9.2V20h13V9.2"/><path d="M9.3 20v-6h5.4v6"/></>,
  catalog: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  create: <><path d="M12 4v16M4 12h16"/><path d="m18 3 .5 1.5L20 5l-1.5.5L18 7l-.5-1.5L16 5l1.5-.5L18 3Z"/></>,
  history: <><path d="M4.5 7.5A8 8 0 1 1 4 15"/><path d="M4.5 3.8v4.3h4.3"/><path d="M12 8v4.5l3 2"/></>,
  profile: <><circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="m4.5 18 5-5 3.5 3 2.5-2.5 4 4.5"/></>,
  video: <><rect x="3" y="5" width="14" height="14" rx="3"/><path d="m17 10 4-2v8l-4-2Z"/></>,
  music: <><path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/></>,
  wallet: <><path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H19v14H6.5A2.5 2.5 0 0 1 4 16.5Z"/><path d="M16 11h5v4h-5a2 2 0 1 1 0-4Z"/></>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  chevron: <path d="m9 6 6 6-6 6"/>,
  heart: <path d="M20.5 9.5c0 5-8.5 10-8.5 10s-8.5-5-8.5-10a4.5 4.5 0 0 1 8.5-2 4.5 4.5 0 0 1 8.5 2Z"/>,
  comment: <path d="M4 5.5h16v11H9l-5 4Z"/>,
  share: <><circle cx="18" cy="5" r="2"/><circle cx="6" cy="12" r="2"/><circle cx="18" cy="19" r="2"/><path d="m8 11 8-5M8 13l8 5"/></>,
  upload: <><path d="M12 16V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/><path d="M5 13v6h14v-6"/></>,
  spark: <><path d="m12 2 1.3 4.2L17.5 7.5l-4.2 1.3L12 13l-1.3-4.2-4.2-1.3 4.2-1.3Z"/><path d="m18.5 13 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7Z"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1A7 7 0 0 0 15 6l-.4-2.6h-4L10.2 6a7 7 0 0 0-1.6 1.1l-2.4-1-2 3.4 2 1.5A7 7 0 0 0 6 12c0 .3 0 .7.1 1l-2 1.5 2 3.4 2.4-1A7 7 0 0 0 10 18l.4 2.6h4L14.8 18a7 7 0 0 0 1.6-1.1l2.4 1 2-3.4-2-1.5c.1-.3.2-.7.2-1Z"/></>,
};

export function Icon({ name, size = 22, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {paths[name]}
    </svg>
  );
}
