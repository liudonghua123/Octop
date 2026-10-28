/** Shared install destination for skill market / URL import UI. */

export type SkillInstallTarget =
  | { type: "agent"; agentId: string }
  | { type: "package"; packageId: string }
  | { type: "browse" };

export function skillHubRankingsPath(target: SkillInstallTarget): string {
  if (target.type === "browse") {
    return `/skills/hub/rankings?type=all`;
  }
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills/hub/rankings?type=all`;
  }
  return `/skill-packages/hub/rankings?type=all`;
}

export function skillHubSearchPath(
  target: SkillInstallTarget,
  query: string,
  limit = 50,
): string {
  const q = encodeURIComponent(query);
  if (target.type === "browse") {
    return `/skills/hub/search?q=${q}&limit=${limit}`;
  }
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills/hub/search?q=${q}&limit=${limit}`;
  }
  return `/skill-packages/hub/search?q=${q}&limit=${limit}`;
}

export function skillHubSearchAllPath(
  target: SkillInstallTarget,
  query: string,
  limit = 50,
): string {
  const q = encodeURIComponent(query);
  if (target.type === "browse") {
    return `/skills/hub/search/all?q=${q}&limit=${limit}`;
  }
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills/hub/search/all?q=${q}&limit=${limit}`;
  }
  return `/skill-packages/hub/search/all?q=${q}&limit=${limit}`;
}

export function skillHubPreviewPath(params: {
  skillName?: string;
  bundleUrl?: string;
}): string {
  const qs = new URLSearchParams();
  if (params.skillName) qs.set("skill_name", params.skillName);
  if (params.bundleUrl) qs.set("bundle_url", params.bundleUrl);
  return `/skills/hub/preview?${qs.toString()}`;
}

export function skillHubInstallPath(target: SkillInstallTarget): string {
  if (target.type === "browse") {
    throw new Error("SkillHub browse target cannot install");
  }
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills/hub/install`;
  }
  return `/skill-packages/${target.packageId}/skills/hub/install`;
}

export function skillListPath(target: SkillInstallTarget): string {
  if (target.type === "browse") {
    throw new Error("SkillHub browse target has no installed list");
  }
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills`;
  }
  return `/skill-packages/${target.packageId}/skills`;
}
