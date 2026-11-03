import test from "node:test";
import assert from "node:assert/strict";
import { effectiveProfile, modeReadiness } from "../moss_go/web/equipment.js";

test("FLUX 3 full-caption bypass uses its own readiness without hiding core gaps", () => {
  const system = {
    engines: {
      "flux3-klein": {
        profiles: {
          balanced: {
            missing: [{ filename: "upsampler.safetensors" }],
            modes: { create: { ready: false } },
            caption_only: {
              missing: [],
              modes: {
                create: { ready: true },
                refine: { ready: false, missing_nodes: ["MossGoFeatherMask"] },
              },
            },
          },
        },
      },
    },
  };
  assert.equal(
    modeReadiness(system, "flux3-klein", "balanced", "create", true).ready,
    false,
  );
  assert.equal(
    modeReadiness(system, "flux3-klein", "balanced", "create", false).ready,
    true,
  );
  assert.equal(
    modeReadiness(system, "flux3-klein", "balanced", "refine", false).ready,
    false,
  );
});

test("unknown hardware stays conservative and cached VRAM does not downgrade capacity", () => {
  assert.equal(effectiveProfile(null, "auto"), "economy");
  assert.equal(
    effectiveProfile(
      { devices: [{ type: "cpu", vram_total: 64 * 1024 ** 3 }] },
      "auto",
    ),
    "economy",
  );
  assert.equal(
    effectiveProfile(
      { devices: [{ type: "cuda", vram_total: 16 * 1024 ** 3, vram_free: 0 }] },
      "auto",
    ),
    "balanced",
  );
  assert.equal(
    effectiveProfile({ hardware: { recommended_profile: "economy" } }, "auto"),
    "economy",
  );
  assert.equal(effectiveProfile(null, "quality"), "quality");
});

test("a missing edit node blocks refinement without blocking creation", () => {
  const system = {
    engines: {
      "flux-klein": {
        profiles: {
          balanced: {
            ready: true,
            models: { model: "fp8" },
            missing: [],
            modes: {
              create: { ready: true, supported: true, missing_nodes: [] },
              refine: {
                ready: false,
                supported: true,
                missing_nodes: ["CropMask"],
              },
            },
          },
        },
      },
    },
  };
  assert.equal(
    modeReadiness(system, "flux-klein", "balanced", "create").ready,
    true,
  );
  assert.equal(
    modeReadiness(system, "flux-klein", "balanced", "refine").ready,
    false,
  );
  assert.deepEqual(
    modeReadiness(system, "flux-klein", "balanced", "refine").missing_nodes,
    ["CropMask"],
  );
  assert.equal(
    modeReadiness(system, "flux-klein", "balanced", "refine").models.model,
    "fp8",
  );
  assert.equal(
    modeReadiness(null, "flux-klein", "balanced", "refine").ready,
    undefined,
  );
});
