import { ApiClientError } from "../api/client";
import { deriveTestSemanticState, ensureTestResult, errorGuidance } from "./testWorkflow";

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

  it("separates expected deny from a passing dropped result", () => {
    expect(deriveTestSemanticState({
      ok: false,
      message: "Ping thất bại theo policy",
      error_code: "POLICY_DENIED",
      result: { reachable: false },
    }, false)).toEqual({
      testCase: "PASS",
      actualNetwork: "DROPPED",
      expectedPolicy: "DENY",
      backendApi: "OK",
      backendOk: true,
    });
  });

  it("treats an HTTP error as unobserved instead of trusting stale network text", () => {
    expect(deriveTestSemanticState({
      ok: false,
      message: "PING THÀNH CÔNG",
      error_code: "HTTP_503",
      http_status: 503,
      result: { reachable: true },
    }, false)).toEqual({
      testCase: "ERROR",
      actualNetwork: "NOT OBSERVED",
      expectedPolicy: "DENY",
      backendApi: "HTTP 503",
      backendOk: false,
    });
  });

  it("marks an unexpected reachable result against DENY policy as FAIL", () => {
    const state = deriveTestSemanticState({ ok: true, message: "Ping thành công", result: { reachable: true } }, false);
    expect(state.testCase).toBe("FAIL");
    expect(state.actualNetwork).toBe("REACHABLE");
    expect(state.expectedPolicy).toBe("DENY");
    expect(state.backendApi).toBe("OK");
  });
});
