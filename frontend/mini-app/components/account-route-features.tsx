"use client";

import { CustomerParityHub } from "./customer-parity-hub";
import { PartnerRoxTransfer } from "./partner-rox-transfer";

export default function AccountRouteFeatures({ route }: { route: "profile" | "partners" | "history" }) {
  return (
    <>
      <CustomerParityHub />
      {route === "partners" ? <PartnerRoxTransfer /> : null}
    </>
  );
}
