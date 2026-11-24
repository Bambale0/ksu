"use client";

import { useEffect, useRef, useState } from "react";

const MOBILE_MEDIA = "(max-width: 767px) and (orientation: portrait)";

/**
 * Cosmetic boot screen. App readiness is owned by the calling boundary, NOT by
 * playback events; a broken or blocked video can never hold navigation open.
 */
export function RoxyLoadingVideo({ message = "Студия творчества" }: { message?: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      video.pause();
      setFallback(true);
      return;
    }

    // Safari/Telegram WebView may block autoplay (including low-power mode).
    // Show the static ROXY mark instead of waiting for a playback callback.
    const start = video.play();
    if (start && typeof start.catch === "function") {
      void start.catch(() => setFallback(true));
    }
    return () => video.pause();
  }, []);

  return (
    <div
      className={`splash splash-video${playing && !fallback ? " splash-video-playing" : ""}${fallback ? " splash-video-fallback" : ""}`}
      role="status"
      aria-label="ROXY загружается"
    >
      <span className="splash-video-fallback-mark" aria-hidden="true"><span>RX</span></span>
      <video
        ref={videoRef}
        className="splash-video-media"
        autoPlay
        muted
        playsInline
        loop
        preload="auto"
        aria-hidden="true"
        onLoadedData={() => setPlaying(true)}
        onPlaying={() => setPlaying(true)}
        onError={() => setFallback(true)}
      >
        <source src="/mini-app/loading/roxy-loading-mobile-9x16.mp4" type="video/mp4" media={MOBILE_MEDIA} />
        <source src="/mini-app/loading/roxy-loading-mobile-9x16.webm" type="video/webm" media={MOBILE_MEDIA} />
        <source src="/mini-app/loading/roxy-loading-web-16x9.webm" type="video/webm" />
        <source src="/mini-app/loading/roxy-loading-web-16x9.mp4" type="video/mp4" />
      </video>
      <span className="splash-video-accessible">ROXY · {message}</span>
    </div>
  );
}