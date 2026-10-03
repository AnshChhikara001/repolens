# A web app in FastAPI with a plain page

The demo needs a page where a visitor picks a repo, asks a question and checks the cited answer. It is one FastAPI app (`repolens web`) serving one static HTML page with hand-written CSS and a small vanilla JavaScript file. There is no build step and no frontend framework.

`run()` takes an optional `on_event` callback that gets each Run log event as it is written. `POST /api/ask` runs the Run in a thread and streams the Tool calls, Agent steps and model calls as server-sent events, then the Report with the code of each Citation and a GitHub link to its lines at the pinned commit. The page reads the stream with `fetch`, since `EventSource` can't POST a body or keep an own key out of the URL. Everything from the model or the repo is added to the page as text, never as HTML.

Example answers are Reports in the same form, kept in `src/repolens/web/examples.json` and generated locally with `repolens ask --save-example`. They show without a model call and without reading the code from the database. The demo repos are the Snapshots in that file that are ingested under the current index version, so a visitor can't make the app ingest anything on our OpenAI key.

Demo limits are checked before the Run starts, with the visitor's address taken as the last `X-Forwarded-For` entry (the one a proxy adds), or the connection's address without a proxy. The app must run as one process, since the limits count Runs in memory (#33).

## Considered Options

- **Streamlit** (the plan in ADR-0009): fast to start, but a Run blocks its script, live progress needs workarounds, and its look is recognisably Streamlit.
- **A React or HTMX frontend:** a build step or another dependency for one page with three states.
- **WebSockets:** two-way, but the page only listens once it has asked.

## Consequences

- The page's JavaScript is tested in a real browser with pytest-playwright, so CI installs Chromium.
- A visitor who closes the page doesn't stop the Run; it finishes and writes its log.
- Example answers carry their code and pinned links, so they stay right when a Snapshot is ingested again. A demo repo at a new commit needs new ones.
