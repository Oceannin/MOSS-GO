export const API = "/moss-go/api/v1";
export async function request(path, data, options = {}) {
  const response = await fetch(API + path, {
    ...options,
    ...(data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error?.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.code = result.error?.code;
    error.field = result.error?.field;
    throw error;
  }
  return result;
}
export async function uploadImage(file, kind = "image") {
  const body = new FormData();
  body.append(kind, file, file.name || "image.png");
  return request("/images", undefined, { method: "POST", body });
}
export function imageURL(id) {
  return `${API}/images/${encodeURIComponent(id)}`;
}
export function downloadJSON(value, name) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
