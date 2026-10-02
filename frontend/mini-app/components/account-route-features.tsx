"use client";

import { CustomerParityHub } from "./customer-parity-hub";
import { PartnerRoxTransfer } from "./partner-rox-transfer";

export default function AccountRouteFeatures({ route }: { route: string }) {
  return (
    <>
      <CustomerParityHub />
      {route === "partners" ? <PartnerRoxTransfer /> : null}
    </>
  );
}
