import type { Decision } from "../api/client";

/**
 * Keeps the animation faithful to the backend decision. A denied packet can
 * only be shown up to the enforcement node; React does not invent a route.
 */
export function animationPath(decision?: Decision): string[] {
  if (!decision || !Array.isArray(decision.path)) return [];
  const path = decision.path.filter((node): node is string => typeof node === "string" && node.length > 0);
  if (decision.action !== "deny" || !decision.blocked_at) return path;
  const blockedIndex = path.indexOf(decision.blocked_at);
  return blockedIndex >= 0 ? path.slice(0, blockedIndex + 1) : path;
}
