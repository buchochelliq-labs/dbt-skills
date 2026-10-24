import React from "react";
import { Button } from "./components";
import type { Approval } from "./contracts";

export function MappingReviewActions({ status, onReview, onRemove }: {
  status: Approval;
  onReview: () => void;
  onRemove: () => void;
}) {
  if (status !== "Draft" && status !== "Needs review") return null;
  return <>
    <Button onClick={onReview}>Review mapping</Button>
    {status === "Draft" && <Button onClick={onRemove}>Remove draft</Button>}
  </>;
}
