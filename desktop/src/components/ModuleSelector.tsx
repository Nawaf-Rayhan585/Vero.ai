import { useState } from "react";
import { useUpdateCamera } from "../hooks/useCameras";
import { AI_MODULES } from "../modules";
import type { AIModule, Camera } from "../api/types";
import { ErrorNotice } from "./ui";

/** Per-camera choice of which AI modules run. Saved to the camera as soon as a box is
 * ticked; like lines and zones, the running session only picks it up on the next Start. */
export function ModuleSelector({ camera, isRunning }: { camera: Camera; isRunning: boolean }) {
  const updateCamera = useUpdateCamera();

  // What was just clicked, held until its save settles. Local state rather than the
  // mutation's pending state: that only updates a tick after the click, and a controlled
  // checkbox snaps back to its old value in between, so the box wouldn't visibly change.
  // It also lets a second quick click build on the first instead of on the stale selection.
  const [pending, setPending] = useState<AIModule[] | null>(null);
  const selected = pending ?? camera.enabled_modules;

  function toggle(module: AIModule, checked: boolean) {
    const next = AI_MODULES.map((m) => m.id).filter((id) => (id === module ? checked : selected.includes(id)));
    setPending(next);
    // Settled (success or failure) hands display back to the saved selection: on success
    // the camera list has already been refetched by then, on failure this reverts the box.
    updateCamera.mutate({ id: camera.id, body: { enabled_modules: next } }, { onSettled: () => setPending(null) });
  }

  return (
    <fieldset className="module-selector">
      <legend>AI modules</legend>
      <div className="module-selector__options">
        {AI_MODULES.map((module) => (
          <label key={module.id} className="module-selector__option">
            <input
              type="checkbox"
              checked={selected.includes(module.id)}
              onChange={(e) => toggle(module.id, e.currentTarget.checked)}
            />{" "}
            {module.label}
          </label>
        ))}
      </div>
      {isRunning && <p className="camera-row__details">Changes apply the next time tracking starts.</p>}
      {updateCamera.isError && <ErrorNotice message={updateCamera.error.message} />}
    </fieldset>
  );
}
