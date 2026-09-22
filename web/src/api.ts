import type { SolveRequest, SolveResponse } from "./types";

export async function solve(payload: SolveRequest): Promise<SolveResponse> {
  const res = await fetch("/api/v1/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  // The API always answers with a JSON body, including 400/422 failures.
  const body = (await res.json()) as SolveResponse;
  return body;
}
