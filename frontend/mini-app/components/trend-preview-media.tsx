"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  className: string;
  mediaType: string | null | undefined;
  url: string;
  thumbnailUrl?: string | null;
};

function retryUrl(url: string, attempt: number): string {
  return attempt ? `${url}${url.includes("?") ? "&" : "?"}retry=${attempt}` : url;
}

export function TrendPreviewMedia({ className, mediaType, url, thumbnailUrl }: Props) {
  const [thumbnailFailed, setThumbnailFailed] = useState(false);
  const [imageRetry, setImageRetry] = useState(0);
  const [poster, setPoster] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const retryTimer = useRef<number | null>(null);

  useEffect(() => {
    setThumbnailFailed(false);
    setImageRetry(0);
    setPoster(null);
    return () => {
      if (retryTimer.current !== null) window.clearTimeout(retryTimer.current);
    };
  }, [thumbnailUrl, url]);

  useEffect(() => {
    if (mediaType !== "video") return;
    const video = videoRef.current;
    if (!video) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      rootMargin: "120px",
    });
    observer.observe(video);
    return () => observer.disconnect();
  }, [mediaType]);

  useEffect(() => {
    if (mediaType !== "video" || !visible || !thumbnailUrl || poster) return;
    let cancelled = false;
    let timer: number | null = null;
    const load = (attempt: number) => {
      const image = new Image();
      image.onload = () => { if (!cancelled) setPoster(thumbnailUrl); };
      image.onerror = () => {
        if (!cancelled && attempt < 6) timer = window.setTimeout(() => load(attempt + 1), 1000);
      };
      image.src = retryUrl(thumbnailUrl, attempt);
    };
    load(0);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [mediaType, visible, thumbnailUrl, poster]);

  if (mediaType === "video") {
    return <video
      ref={videoRef}
      className={className}
      src={visible ? url : undefined}
      poster={poster || undefined}
      muted
      autoPlay
      loop
      playsInline
      preload="none"
    />;
  }

  return <img
    className={className}
    src={thumbnailUrl && !thumbnailFailed ? retryUrl(thumbnailUrl, imageRetry) : url}
    alt=""
    loading="lazy"
    decoding="async"
    onError={() => {
      if (!thumbnailUrl || thumbnailFailed || retryTimer.current !== null) return;
      if (imageRetry >= 3) {
        setThumbnailFailed(true);
      } else {
        retryTimer.current = window.setTimeout(() => {
          retryTimer.current = null;
          setImageRetry((current) => current + 1);
        }, 600);
      }
    }}
  />;
}
