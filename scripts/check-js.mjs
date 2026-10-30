import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("../moss_go/web/", import.meta.url));
let failed = false;
for (const file of readdirSync(root).filter((name) => name.endsWith(".js"))) {
  const result = spawnSync(process.execPath, ["--check", root + file], {
    stdio: "inherit",
  });
  if (result.status !== 0) failed = true;
}
process.exitCode = failed ? 1 : 0;
