const KEY = "moss-go.pending-launch.v1";

export class LaunchController {
  constructor(request, storage) {
    this.request = request;
    this.pending = null;
    this.persisted = false;
    try {
      this.storage = storage ?? globalThis.localStorage;
      const raw = this.storage?.getItem(KEY);
      if (!raw || raw.length > 128000) return;
      const value = JSON.parse(raw);
      if (
        value &&
        /^[a-f0-9]{32}$/.test(value.request_id) &&
        ["create", "reference", "refine"].includes(value.mode) &&
        typeof value.prompt === "string"
      ) {
        this.pending = value;
        this.persisted = true;
      }
    } catch {}
  }

  prepare(settings) {
    if (this.pending) return;
    this.pending = JSON.parse(JSON.stringify(settings));
    try {
      if (this.storage) {
        this.storage.setItem(KEY, JSON.stringify(this.pending));
        this.persisted = true;
      }
    } catch {}
  }

  clear() {
    this.pending = null;
    this.persisted = false;
    try {
      this.storage?.removeItem(KEY);
    } catch {}
  }

  async send() {
    if (!this.pending) throw new Error("No launch to recover");
    const pending = this.pending;
    try {
      const result = await this.request("/jobs", pending);
      if (this.pending?.request_id === pending.request_id) this.clear();
      return result;
    } catch (error) {
      // An explicit validation rejection did not create a batch. Network/server
      // failures keep the exact snapshot and identifier for safe recovery.
      if (
        error.status >= 400 &&
        error.status < 500 &&
        error.code !== "request_conflict" &&
        this.pending?.request_id === pending.request_id
      )
        this.clear();
      throw error;
    }
  }

  async reconcile() {
    if (!this.pending) return null;
    const requestId = this.pending.request_id;
    const result = await this.request(`/requests/${requestId}`);
    if (!result.batch || this.pending?.request_id !== requestId) return null;
    this.clear();
    return result.batch;
  }
}
