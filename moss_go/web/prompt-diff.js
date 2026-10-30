export function diffWords(before, after) {
  const left = before.match(/\S+\s*|\s+/gu) || [];
  const right = after.match(/\S+\s*|\s+/gu) || [];
  let start = 0,
    end = 0;
  while (
    start < Math.min(left.length, right.length) &&
    left[start] === right[start]
  )
    start++;
  while (
    end < Math.min(left.length, right.length) - start &&
    left[left.length - end - 1] === right[right.length - end - 1]
  )
    end++;
  const a = left.slice(start, left.length - end),
    b = right.slice(start, right.length - end),
    result = [];
  function push(kind, text) {
    if (!text) return;
    const last = result.at(-1);
    if (last?.kind === kind) last.text += text;
    else result.push({ kind, text });
  }
  push("equal", left.slice(0, start).join(""));
  // Bound work for long translations; both exact texts are still reviewable.
  if (a.length * b.length > 160000) {
    push("delete", a.join(""));
    push("insert", b.join(""));
  } else {
    const rows = Array.from(
      { length: a.length + 1 },
      () => new Uint16Array(b.length + 1),
    );
    for (let i = a.length - 1; i >= 0; i--)
      for (let j = b.length - 1; j >= 0; j--)
        rows[i][j] =
          a[i] === b[j]
            ? 1 + rows[i + 1][j + 1]
            : Math.max(rows[i + 1][j], rows[i][j + 1]);
    let i = 0,
      j = 0;
    while (i < a.length || j < b.length) {
      if (i < a.length && j < b.length && a[i] === b[j]) {
        push("equal", a[i++]);
        j++;
      } else if (
        i < a.length &&
        (j === b.length || rows[i + 1][j] >= rows[i][j + 1])
      )
        push("delete", a[i++]);
      else push("insert", b[j++]);
    }
  }
  push("equal", end ? left.slice(-end).join("") : "");
  return result;
}

export function renderPromptDiff(container, before, after, labels) {
  container.replaceChildren();
  const operations = diffWords(before, after);
  container.classList.toggle(
    "block-review",
    operations.length === 2 &&
      operations[0].kind === "delete" &&
      operations[1].kind === "insert",
  );
  for (const operation of operations) {
    if (operation.kind === "equal") {
      container.append(document.createTextNode(operation.text));
      continue;
    }
    const mark = document.createElement(
      operation.kind === "insert" ? "ins" : "del",
    );
    const prefix = document.createElement("span");
    prefix.className = "sr-only";
    prefix.textContent = `${labels[operation.kind]}: `;
    mark.append(prefix, document.createTextNode(operation.text));
    container.append(mark);
  }
}
