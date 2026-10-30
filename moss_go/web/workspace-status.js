// Keep the idle message consistent with the next action a person can take.
export function workspaceStatus({
  pending,
  activeStatus,
  uploading,
  requesting,
  system,
  ready,
  error,
  mode,
  hasInput,
  hasMask,
  prompt,
}) {
  if (pending) return "recoveringLaunch";
  if (activeStatus) return activeStatus;
  if (uploading) return "uploading";
  if (requesting) return "submitting";
  if (!system) return "connecting";
  if (!system.connected) return "disconnected";
  if (!ready) return "configure";
  if (error) return "reviewError";
  if (mode !== "create" && !hasInput) return "chooseInput";
  if (mode === "refine" && !hasMask) return "chooseArea";
  if (!prompt?.trim()) return "enterDescription";
  return "ready";
}
