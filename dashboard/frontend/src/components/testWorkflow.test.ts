import { ApiClientError } from "../api/client";
import { ensureTestResult, errorGuidance } from "./testWorkflow";

describe("network test contract", () => {
  it("accepts a valid backend measurement response", () => {
    const payload = { ok: true, message: "Ping thành công", result: { rtt_avg_ms: 12 } };
    expect(ensureTestResult(payload)).toBe(payload);
  });

  it("rejects malformed API responses without inventing a result", () => {
    expect(() => ensureTestResult({ message: "missing ok" })).toThrow(ApiClientError);
    try {
      ensureTestResult(null);
    } catch (error) {
      expect(error).toBeInstanceOf(ApiClientError);
      expect((error as ApiClientError).errorCode).toBe("MALFORMED_RESPONSE");
    }
  });

  it.each([
    ["AGENT_TIMEOUT", "Agent"],
    ["BACKEND_OFFLINE", "FastAPI backend"],
    ["IPERF_BUSY", "iperf"],
    ["POLICY_DENIED", "Policy"],
    ["AUTH_INVALID", "Token"],
  ])("provides an operator action for %s", (code, expectedText) => {
    expect(errorGuidance(code)).toContain(expectedText);
  });
});
