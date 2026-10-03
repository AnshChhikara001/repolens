"use strict";

// Everything from the model or the repo goes into the page as text, never as HTML.

const $ = (id) => document.getElementById(id);
const form = $("ask");
const question = $("question");
const submit = $("submit");
const apiKey = $("api-key");
const notice = $("notice");
const progress = $("progress");
const steps = $("steps");
const usage = $("usage");
const answer = $("answer");

let repos = [];
let running = null; // the AbortController of the question being answered

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  node.append(...present(children));
  return node;
}

const present = (children) => children.filter((child) => child !== null && child !== undefined);

const number = (n) => n.toLocaleString("en-US");
const plural = (n, word) => `${number(n)} ${word}${n === 1 ? "" : "s"}`;
const shortSnapshot = (snapshot) => snapshot.replace(/@(\w{7})\w*$/, "@$1");
const selected = () => repos.find((repo) => repo.snapshot === form.elements.repo?.value);

function say(message) {
  notice.textContent = message;
  notice.hidden = !message;
}

// Repos and their example answers

async function loadRepos() {
  const list = $("repos");
  try {
    const response = await fetch("/api/repos");
    if (!response.ok) throw new Error(response.statusText);
    repos = await response.json();
  } catch {
    list.replaceChildren(el("p", { class: "quiet" }, "The repos can't be loaded. Check that the server and its database are running, then reload."));
    return;
  }
  if (repos.length === 0) {
    list.replaceChildren(el("p", { class: "quiet" }, "No demo repo is ingested yet. Ingest one with repolens ingest, then reload."));
    submit.disabled = true;
    return;
  }
  list.replaceChildren(
    ...repos.map((repo, i) =>
      el("label", { class: "repo", title: `Pinned at commit ${repo.sha}` },
        el("input", { type: "radio", name: "repo", value: repo.snapshot, checked: i === 0 }),
        el("span", { translate: false }, repo.repo),
      ),
    ),
  );
  showRepo();
}

function showRepo() {
  const repo = selected();
  const section = $("examples");
  section.hidden = !repo || repo.examples.length === 0;
  if (section.hidden) return;
  const models = [...new Set(repo.examples.map((example) => example.model))];
  $("examples-model").textContent = models.join(" and ");
  $("example-list").replaceChildren(
    ...repo.examples.map((example) =>
      el("li", {},
        el("button", { type: "button", class: "example", onclick: () => showExample(example) }, example.question),
      ),
    ),
  );
  showExample(repo.examples[0], false);
}

function showExample(example, focus = true) {
  running?.abort();
  say("");
  progress.hidden = true;
  renderAnswer(example, { saved: true });
  if (focus) answer.focus();
}

// Asking a question

form.addEventListener("change", (event) => {
  if (event.target.name === "repo") showRepo();
});

question.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const repo = selected();
  const text = question.value.trim();
  if (!repo || submit.disabled) return;
  if (!text) {
    say("Type a question about the code first.");
    question.focus();
    return;
  }
  running?.abort();
  const controller = new AbortController();
  running = controller;
  say("");
  steps.replaceChildren();
  usage.textContent = "";
  progress.querySelector("h2").textContent = "Looking through the code";
  progress.hidden = false;
  submit.disabled = true;
  submit.textContent = "Asking…";
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot: repo.snapshot, question: text, api_key: apiKey.value.trim() || null }),
      signal: controller.signal,
    });
    if (!response.ok) {
      await refused(response);
      return;
    }
    answer.hidden = true;
    const ended = await follow(response.body, controller.signal);
    if (!ended && !controller.signal.aborted) {
      progress.hidden = true;
      say("The answer stopped before it was done. Try again.");
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      progress.hidden = true;
      say("The connection to the server broke off. Try again.");
    }
  } finally {
    if (running === controller) {
      running = null;
      submit.disabled = false;
      submit.textContent = "Ask";
    }
  }
});

async function refused(response) {
  progress.hidden = true;
  let detail = "";
  try {
    const body = await response.json();
    detail = typeof body.detail === "string" ? body.detail : "";
  } catch {
    // not JSON; fall back to the status below
  }
  if (response.status === 429) {
    say(detail);
    $("own-key").open = true;
    apiKey.focus();
  } else if (response.status === 422) {
    say(question.value.trim().length > 500
      ? "Questions can be up to 500 characters long."
      : "The question couldn't be sent. Check it and the API key, then try again.");
  } else {
    say(detail || `The server refused the question (${response.status}).`);
  }
}

// Reads the server-sent events of a Run: its steps, then the answer or an error. Returns
// whether one of those last two came.
async function follow(body, signal) {
  const reader = body.pipeThrough(new TextDecoderStream()).getReader();
  const totals = { calls: 0, tokens: 0 };
  let buffer = "";
  let ended = false;
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const message = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const name = message.match(/^event: (.*)$/m)?.[1];
      const data = message.match(/^data: (.*)$/m)?.[1];
      if (name && data) {
        handle(name, JSON.parse(data), totals);
        ended ||= name === "report" || name === "error";
      }
    }
  }
  return ended;
}

function handle(name, data, totals) {
  if (name === "tool") {
    steps.append(el("li", {}, describeTool(data)));
  } else if (name === "step" && data.action === "answer") {
    steps.append(el("li", {}, "Writing the answer from what it found"));
  } else if (name === "call") {
    totals.calls += 1;
    totals.tokens += data.input_tokens + data.output_tokens;
    usage.textContent = `${plural(totals.calls, "model call")} so far, ${number(totals.tokens)} tokens.`;
  } else if (name === "report") {
    progress.querySelector("h2").textContent = "Looked through the code";
    usage.textContent = "";
    renderAnswer(data, { saved: false });
    answer.focus();
  } else if (name === "error") {
    progress.hidden = true;
    say(data.message);
  }
}

function describeTool({ tool, args, shown }) {
  const found = shown.length === 0 ? "nothing new" : plural(shown.length, "excerpt");
  if (tool === "search_code") return `Searched for “${args.query}” and found ${found}`;
  if (tool === "read_lines") return `Read ${args.path}, lines ${args.start_line} to ${args.end_line}: ${found}`;
  if (tool === "find_definition") return `Looked up where ${args.name} is defined: ${found}`;
  return `${tool}: ${found}`;
}

// The answer

function renderAnswer(data, { saved }) {
  const findings = el("ol", { class: "findings" },
    ...data.findings.map((finding, i) =>
      el("li", { class: "finding", id: `finding-${i + 1}` },
        el("p", { class: "claim" }, ...withCode(finding.claim)),
        ...finding.citations.map(renderCitation),
      ),
    ),
  );
  const source = saved ? `Example answer by ${data.model}` : `Answered just now by ${data.model}`;
  answer.replaceChildren(...present([
    el("h2", { class: "asked" }, data.question),
    el("p", { class: "byline" }, `${source}, about ${shortSnapshot(data.snapshot)}.`),
    el("p", { class: "prose" }, ...withMarkers(data.answer, data.findings.length)),
    data.findings.length ? findings : null,
    el("p", { class: "quiet" }, usageLine(data)),
    data.rejected
      ? el("p", { class: "quiet" }, `The verifier dropped ${plural(data.rejected, "citation")} that pointed at lines the model was never shown.`)
      : null,
    el("p", { class: "quiet terminal" }, "Ask the same in a terminal: ",
      el("code", { translate: false }, `repolens ask ${shortSnapshot(data.snapshot)} ${shellQuote(data.question)}`)),
  ]));
  answer.hidden = false;
}

// Turns "[1]" in the answer into a link that opens the first citation of Finding 1, and
// `name` into code.
function withMarkers(text, count) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(/\[(\d+)\]|`([^`\n]+)`/g)) {
    let part;
    if (match[2] !== undefined) {
      part = el("code", { translate: false }, match[2]);
    } else {
      const n = Number(match[1]);
      if (n < 1 || n > count) continue;
      part = el("a", {
        class: "marker", href: `#finding-${n}`, "aria-label": `Finding ${n}`,
        onclick: (event) => openFinding(event, n),
      }, String(n));
    }
    parts.push(text.slice(last, match.index), part);
    last = match.index + match[0].length;
  }
  parts.push(text.slice(last));
  return parts;
}

// Claims can name code in backticks too.
const withCode = (text) => withMarkers(text, 0);

function openFinding(event, n) {
  event.preventDefault();
  const finding = $(`finding-${n}`);
  const first = finding.querySelector("details");
  if (first) first.open = true;
  finding.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  first?.querySelector("summary").focus({ preventScroll: true });
}

function renderCitation(citation) {
  const range = citation.start_line === citation.end_line
    ? `${citation.start_line}`
    : `${citation.start_line}–${citation.end_line}`;
  const lines = citation.code.split("\n");
  const width = String(citation.start_line + lines.length - 1).length;
  return el("details", { class: "citation" },
    el("summary", {},
      el("code", { class: "path", translate: false }, `${citation.path}:${range}`),
      citation.symbol ? el("span", { class: "symbol" }, ` in ${citation.symbol}`) : null,
    ),
    el("pre", { class: "code", translate: false, tabindex: "0", "aria-label": `${citation.path}, lines ${range}` },
      ...lines.map((line, i) =>
        el("span", { class: "line" },
          el("span", { class: "ln", "aria-hidden": "true" }, String(citation.start_line + i).padStart(width)),
          `${line}\n`,
        ),
      ),
    ),
    el("a", { class: "github", href: citation.url }, "Open these lines on GitHub"),
  );
}

function usageLine(data) {
  if (data.calls === 0) return `No model calls, ${data.duration_s.toFixed(1)} s.`;
  return `${plural(data.calls, "model call")}, ${number(data.input_tokens)} tokens in and ${number(data.output_tokens)} out, ${data.duration_s.toFixed(1)} s.`;
}

// Double quotes read best; single quotes when the text has characters a shell expands there.
function shellQuote(text) {
  if (!/["$`\\!]/.test(text)) return `"${text}"`;
  return `'${text.replaceAll("'", `'\\''`)}'`;
}

loadRepos();
