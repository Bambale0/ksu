"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  className: string;
  mediaType: string | null | undefined;
  url: string;
  thumbnailUrl?: string | null;
};

export function TrendPreviewMedia({ className, mediaType, url, thumbnailUrl }: Props) {
  const [thumbnailFailed, setThumbnailFailed] = useState(false);
  const [visible, setVisible] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

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

  if (mediaType === "video") {
    return <video
      ref={videoRef}
      className={className}
      src={visible ? url : undefined}
      poster={thumbnailUrl || undefined}
      muted
      autoPlay
      loop
      playsInline
      preload="none"
    />;
  }

  return <img
    className={className}
    src={thumbnailUrl && !thumbnailFailed ? thumbnailUrl : url}
    alt=""
    loading="lazy"
    decoding="async"
    onError={() => setThumbnailFailed(true)}
  />;
}
