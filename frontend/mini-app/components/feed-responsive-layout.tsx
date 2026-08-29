"use client";

export function FeedResponsiveLayout() {
  return <style>{`
    .tiktok-feed-meta {
      bottom: calc(94px + var(--tg-safe-bottom, 0px) + var(--feed-admin-clearance, 0px));
    }

    .tiktok-feed-rail {
      bottom: calc(95px + var(--tg-safe-bottom, 0px) + var(--feed-admin-clearance, 0px));
    }

    .tiktok-feed-loader {
      bottom: calc(88px + var(--tg-safe-bottom, 0px) + var(--feed-admin-clearance, 0px));
    }

    @media (max-width: 560px) and (orientation: portrait) {
      .tiktok-feed-media {
        background:
          radial-gradient(circle at 50% 34%, rgba(123, 65, 191, .12), transparent 38%),
          #050507;
      }

      .tiktok-feed-media > video {
        background: transparent;
      }

      .tiktok-feed-media > video,
      .tiktok-feed-media > img.tiktok-feed-main-image {
        object-position: center 34%;
      }

      .tiktok-feed-meta {
        right: 72px;
        gap: 6px;
      }

      .tiktok-feed-rail {
        right: max(7px, var(--tg-safe-right, 0px));
        width: 54px;
        gap: 7px;
      }

      .tiktok-feed-rail-action {
        width: 48px;
        min-height: 47px;
      }

      .tiktok-feed-rail-action > span:first-child {
        width: 41px;
        height: 41px;
      }

      .tiktok-feed-avatar {
        width: 50px;
        height: 58px;
      }

      .tiktok-feed-avatar > span:first-child {
        width: 44px;
        height: 44px;
      }
    }

    @media (max-width: 390px) and (orientation: portrait) {
      .tiktok-feed-media > video,
      .tiktok-feed-media > img.tiktok-feed-main-image {
        object-position: center 31%;
      }

      .tiktok-feed-meta {
        left: max(12px, var(--tg-safe-left, 0px));
        right: 68px;
      }
    }
  `}</style>;
}
