import type { Decision } from "../api/client";
import { animationPath } from "./packetPath";

describe("animationPath", () => {
  it("truncates a denied backend path at the enforcement node", () => {
    const decision: Decision = {
      action: "deny",
      reason: "policy",
      path: ["h20_01", "access_floor1", "core_hq", "infra_access", "h90"],
      blocked_at: "core_hq",
    };
    expect(animationPath(decision)).toEqual(["h20_01", "access_floor1", "core_hq"]);
  });

  it("keeps an allowed backend path intact", () => {
    const decision: Decision = {
      action: "allow",
      reason: "voice",
      path: ["h20_01", "access_floor1", "core_hq", "infra_access", "h90"],
    };
    expect(animationPath(decision)).toEqual(decision.path);
  });
});
