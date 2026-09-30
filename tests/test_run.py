import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fakes import SHA, FakeEmbedder, FixtureSource, KeywordReranker, ScriptedLLM

from repolens import chunking, tools
from repolens.code_navigator import AgentAction, CodeFindings
from repolens.ingest import ingest
from repolens.report import Citation, Finding, Report
from repolens.report_writer import ReportDraft
from repolens.run import RunConfig, run
from repolens.snapshot import RepoRef, Snapshot
from repolens.store import ChunkStore

SNAPSHOT = Snapshot("acme", "shop", SHA)
QUESTION = "How are passwords stored?"

HASHING = Citation(path="app/auth.py", start_line=6, end_line=7, symbol="hash_password")
LOGIN = Citation(path="app/auth.py", start_line=14, end_line=15, symbol="LoginService.login")
HASHED = Finding(claim="Passwords are hashed with SHA-256 and a fixed salt.", citations=[HASHING])
CHECKED = Finding(
    claim="Login compares the stored hash with the hash of the given password.",
    citations=[LOGIN, HASHING],
)


# Scores every Chunk the same, so reranking keeps the search order.
SEARCH_ORDER = KeywordReranker()
# Ranks `hash_password` first, so with TOP_K = 1 the Run's first search shows only it.
FIRST_HASHING = KeywordReranker("def hash_password")


@pytest.fixture
def ingested(store: ChunkStore) -> ChunkStore:
    ingest(RepoRef("acme", "shop"), FixtureSource(), FakeEmbedder(), store)
    return store


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


def config(
    store: ChunkStore,
    llm: ScriptedLLM,
    runs_dir: Path,
    reranker: KeywordReranker | None = SEARCH_ORDER,
) -> RunConfig:
    return RunConfig(
        llm=llm, embedder=FakeEmbedder(), store=store, reranker=reranker, runs_dir=runs_dir
    )


def read_log(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def answer(*findings: Finding) -> AgentAction:
    return AgentAction(action="answer", findings=list(findings))


def test_the_code_navigator_reads_more_code_before_it_answers(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    llm = ScriptedLLM(
        AgentAction(action="read", path="app/auth.py", start_line=10, end_line=15),
        answer(CHECKED),
        ReportDraft(answer="Checked [1]."),
    )

    # The first search shows only `hash_password`; `LoginService.login` must be read.
    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, FIRST_HASHING))

    assert "def login" not in llm.prompts[0][1]
    assert "14     def login(self, name: str, password: str) -> bool:" in llm.prompts[1][1]
    assert report.findings == [CHECKED]


def test_report_answers_from_cited_findings(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(
        answer(HASHED, CHECKED),
        ReportDraft(answer="Passwords are stored as salted SHA-256 hashes [1][2]."),
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.question == QUESTION
    assert report.snapshot == SNAPSHOT
    assert report.answer == "Passwords are stored as salted SHA-256 hashes [1][2]."
    assert report.findings == [HASHED, CHECKED]


def search(query: str) -> AgentAction:
    return AgentAction(action="search", query=query)


def schemas(report: Report) -> list[str]:
    return [call.schema for call in report.calls]


@pytest.mark.parametrize("name", ["LoginService", "login", "LoginService.login", " login() "])
def test_the_code_navigator_can_look_up_a_definition(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    llm = ScriptedLLM(
        AgentAction(action="define", name=name), answer(CHECKED), ReportDraft(answer="[1]")
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, FIRST_HASHING))

    assert "14     def login(self, name: str, password: str) -> bool:" in llm.prompts[1][1]
    assert report.findings == [CHECKED]


def test_a_run_stops_after_eight_agent_steps_with_an_answer(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    llm = ScriptedLLM(
        *[search(f"passwords {n}") for n in range(8)],
        CodeFindings(findings=[HASHED]),
        ReportDraft(answer="Hashed [1]."),
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert schemas(report) == ["AgentAction"] * 7 + ["CodeFindings", "ReportDraft"]
    assert "Step 8 of 8, the last: answer with your findings now." in llm.prompts[7][1]
    assert report.findings == [HASHED]
    steps = [e for e in read_log(runs_dir / f"{report.run_id}.jsonl") if e["event"] == "step"]
    assert [e["step"] for e in steps] == list(range(1, 9))
    assert steps[-1]["action"] == "answer"
    assert steps[-1]["step_limit"] is True


def test_with_one_step_the_code_navigator_answers_from_the_first_search(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    llm = ScriptedLLM(CodeFindings(findings=[HASHED]), ReportDraft(answer="Hashed [1]."))

    run_config = replace(config(ingested, llm, runs_dir), max_steps=1)
    report = run(QUESTION, SNAPSHOT, run_config)

    assert schemas(report) == ["CodeFindings", "ReportDraft"]
    assert report.findings == [HASHED]


def test_a_citation_to_lines_outside_a_read_is_dropped(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    whole_class = Citation(path="app/auth.py", start_line=10, end_line=15, symbol="LoginService")
    llm = ScriptedLLM(
        AgentAction(action="read", path="app/auth.py", start_line=14, end_line=15),
        answer(
            Finding(claim=CHECKED.claim, citations=[LOGIN]),
            Finding(claim="LoginService keeps the users.", citations=[whole_class]),
        ),
        ReportDraft(answer="Checked [1]."),
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, FIRST_HASHING))

    assert "12         self.users = users" not in llm.prompts[1][1]
    assert report.findings == [Finding(claim=CHECKED.claim, citations=[LOGIN])]
    assert report.rejected == [whole_class]


@pytest.mark.parametrize(
    ("action", "result"),
    [
        (
            AgentAction(action="read", path="app/missing.py", start_line=1, end_line=5),
            f"There is no file 'app/missing.py' in {SNAPSHOT}.",
        ),
        (
            AgentAction(action="read", path="app/auth.py", start_line=8, end_line=9),
            "app/auth.py has no code in lines 8-9.",
        ),
        (AgentAction(action="read"), "read needs a `path`."),
        (AgentAction(action="search"), "search needs a `query`."),
        (AgentAction(action="define"), "define needs a `name`."),
        (AgentAction(action="define", name="logout"), "No definition of 'logout'."),
    ],
)
def test_a_tool_call_that_finds_nothing_says_why(
    ingested: ChunkStore, runs_dir: Path, action: AgentAction, result: str
) -> None:
    llm = ScriptedLLM(action, answer(HASHED), ReportDraft(answer="Hashed [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert result in llm.prompts[1][1]
    assert report.findings == [HASHED]


def test_code_already_shown_is_not_shown_again(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(search(QUESTION), answer(HASHED), ReportDraft(answer="Hashed [1]."))

    run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    prompt = llm.prompts[1][1]
    assert prompt.count("def hash_password") == 1
    assert "Already shown above: app/auth.py:1-7 hash_password" in prompt


def test_a_search_shows_the_first_lines_of_every_hit(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The six hits have 7, 6, 1, 3, 2 and 4 lines: 23 in all.
    monkeypatch.setattr(tools, "MAX_RESULT_LINES", 12)
    llm = ScriptedLLM(answer(HASHED), ReportDraft(answer="Hashed [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    prompt = llm.prompts[0][1]
    assert prompt.count("<code ") == 6
    assert "1 export const App" in prompt  # short hits are shown whole
    assert "3 SALT" in prompt  # the longest hit gets what the short ones leave
    assert "4 \n" not in prompt
    assert "app/auth.py was cut after line 3. Read lines 4-7 for the rest of hash_password." in (
        prompt
    )
    assert "limit" not in prompt
    assert report.rejected == [HASHING]  # its lines 6-7 weren't shown


def test_a_tool_result_shows_at_most_its_line_limit(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    monkeypatch.setattr(tools, "MAX_RESULT_LINES", 5)
    hashing = Finding(claim=HASHED.claim, citations=[HASHING])
    llm = ScriptedLLM(answer(hashing), ReportDraft(answer="Hashed [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, FIRST_HASHING))

    prompt = llm.prompts[0][1]
    assert "5 \n" in prompt
    assert "6 def hash_password" not in prompt
    assert "app/auth.py was cut after line 5. Read lines 6-7 for the rest of hash_password." in (
        prompt
    )
    assert report.rejected == [HASHING]


def test_a_run_shows_at_most_its_line_limit(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    monkeypatch.setattr(tools, "MAX_RUN_LINES", 7)
    llm = ScriptedLLM(
        AgentAction(action="read", path="app/auth.py", start_line=10, end_line=15),
        answer(Finding(claim=CHECKED.claim, citations=[LOGIN])),
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, FIRST_HASHING))

    assert "The Run has shown its limit of 7 lines." in llm.prompts[1][1]
    assert "def login" not in llm.prompts[1][1]
    assert report.findings == []


def test_code_navigator_reads_the_best_reranked_code_first(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    llm = ScriptedLLM(answer(HASHED), ReportDraft(answer="[1]"))

    # Search ranks the password code first for this question; the reranker prefers the API.
    run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, KeywordReranker("fetch(")))

    prompt = "\n".join(user for _, user in llm.prompts)
    hashing = prompt.index("return hashlib.sha256((SALT + password).encode()).hexdigest()")
    assert prompt.index("fetch(") < hashing


def test_without_a_reranker_the_code_navigator_reads_the_code_in_search_order(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    llm = ScriptedLLM(answer(HASHED), ReportDraft(answer="[1]"))

    run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, reranker=None))

    [(_, prompt)] = llm.prompts[:1]
    assert "def hash_password" in prompt
    assert prompt.count("<code ") == 1


def test_findings_without_citations_are_dropped(ingested: ChunkStore, runs_dir: Path) -> None:
    uncited = Finding(claim="Passwords are stored in plain text.", citations=[])
    llm = ScriptedLLM(answer(uncited, HASHED), ReportDraft(answer="Hashed [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [HASHED]


@pytest.mark.parametrize(
    "citation",
    [
        Citation(path="app/billing.py", start_line=1, end_line=2),
        Citation(path="app/auth.py", start_line=14, end_line=40),
        Citation(path="app/auth.py", start_line=0, end_line=3),
        Citation(path="app/auth.py", start_line=7, end_line=6),
        Citation(path="app/auth.py", start_line=6, end_line=9),  # 8-9 are in no Chunk
        Citation(path="app/auth.py", start_line=6, end_line=7, symbol="LoginService.logout"),
        Citation(path="app/auth.py", start_line=6, end_line=7, symbol="LoginService"),
        Citation(path="app/auth.py", start_line=14, end_line=15, symbol="log"),
        Citation(path="app/auth.py", start_line=6, end_line=7, symbol="password"),
    ],
    ids=lambda citation: f"{citation} {citation.symbol or ''}".strip(),
)
def test_a_made_up_citation_is_dropped(
    ingested: ChunkStore, runs_dir: Path, citation: Citation
) -> None:
    made_up = Finding(claim="Passwords are checked against a billing record.", citations=[citation])
    llm = ScriptedLLM(answer(made_up, CHECKED), ReportDraft(answer="Checked [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [CHECKED]


def test_a_citation_to_lines_the_model_was_not_shown_is_dropped(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    unseen = Finding(claim=CHECKED.claim, citations=[LOGIN])
    llm = ScriptedLLM(answer(HASHED, unseen), ReportDraft(answer="Hashed [1]."))

    # Only `hash_password` is shown, so the real lines of `LoginService.login` can't be cited.
    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, FIRST_HASHING))

    assert "def login" not in llm.prompts[0][1]
    assert report.findings == [HASHED]


def test_only_the_valid_citations_of_a_finding_are_kept(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    made_up = Citation(path="app/auth.py", start_line=90, end_line=95)
    partly = Finding(claim=CHECKED.claim, citations=[LOGIN, made_up])
    llm = ScriptedLLM(answer(partly), ReportDraft(answer="Checked [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [Finding(claim=CHECKED.claim, citations=[LOGIN])]


@pytest.mark.parametrize("symbol", [None, "LoginService", "login", "LoginService.login"])
def test_a_citation_may_name_the_class_or_method_it_points_into(
    ingested: ChunkStore, runs_dir: Path, symbol: str | None
) -> None:
    citation = Citation(path="app/auth.py", start_line=14, end_line=15, symbol=symbol)
    finding = Finding(claim=CHECKED.claim, citations=[citation])
    llm = ScriptedLLM(answer(finding), ReportDraft(answer="Checked [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [finding]


CLIENT_TS = """\
export class Client {
  request(url: string): Promise<Response> {
    const { href } = new URL(url);
    return this.#send(href);
  }

  #send(url: string): Promise<Response> {
    return fetch(url);
  }
}
"""


CLIENT = Snapshot("acme", "client", SHA)


@pytest.fixture
def client_ts(store: ChunkStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ChunkStore:
    # A long class is split into one Chunk per method, named like `Client.#send`.
    monkeypatch.setattr(chunking, "MAX_CHUNK_LINES", 5)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "client.ts").write_text(CLIENT_TS)
    ingest(RepoRef("acme", "client"), FixtureSource(repo), FakeEmbedder(), store)
    return store


@pytest.mark.parametrize(
    ("lines", "symbol", "kept"),
    [
        ((7, 9), "Client.#send", True),
        ((7, 9), "Client.send", True),
        ((7, 9), "send", True),
        ((2, 5), "Client.#request", True),
        ((2, 5), "Client.#", False),
    ],
)
def test_a_typescript_private_name_may_be_cited_with_or_without_its_hash(
    client_ts: ChunkStore, runs_dir: Path, lines: tuple[int, int], symbol: str, kept: bool
) -> None:
    citation = Citation(path="client.ts", start_line=lines[0], end_line=lines[1], symbol=symbol)
    finding = Finding(claim="Requests are sent with fetch.", citations=[citation])
    llm = ScriptedLLM(answer(finding), ReportDraft(answer="Sent [1]."))

    report = run("How are requests sent?", CLIENT, config(client_ts, llm, runs_dir))

    assert report.findings == ([finding] if kept else [])


@pytest.mark.parametrize("name", ["send", "#send", "Client.send", "Client.#send"])
def test_a_typescript_private_method_may_be_looked_up_with_or_without_its_hash(
    client_ts: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    llm = ScriptedLLM(AgentAction(action="define", name=name), answer())
    reranker = KeywordReranker("request(")

    run("How are requests sent?", CLIENT, config(client_ts, llm, runs_dir, reranker))

    assert "8     return fetch(url);" not in llm.prompts[0][1]
    assert "8     return fetch(url);" in llm.prompts[1][1]


def test_no_findings_means_a_not_found_report(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(answer())

    report = run("How is billing done?", SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == []
    assert report.answer == f"Nothing in {SNAPSHOT} answers this question."


def test_findings_with_only_made_up_citations_mean_a_not_found_report(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    made_up = Finding(
        claim="Billing uses Stripe.",
        citations=[Citation(path="app/billing.py", start_line=1, end_line=9)],
    )
    llm = ScriptedLLM(answer(made_up))

    report = run("How is billing done?", SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == []
    assert report.answer == f"Nothing in {SNAPSHOT} answers this question."


def test_a_snapshot_without_chunks_is_answered_without_a_model(
    store: ChunkStore, runs_dir: Path
) -> None:
    report = run(QUESTION, SNAPSHOT, config(store, ScriptedLLM(), runs_dir))

    assert report.findings == []
    assert report.calls == []
    assert "Nothing in" in report.answer
    assert re.search(r"\n\nNo model calls · \d+\.\ds$", str(report))


def test_the_report_ends_with_the_run_usage(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(answer(HASHED), ReportDraft(answer="[1]"))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert [(c.model, c.input_tokens, c.output_tokens) for c in report.calls] == [
        ("fake:scripted", 1000, 100)
    ] * 2
    assert re.search(r"\n\n2 calls · 2,000 in / 200 out tokens · \d+\.\ds$", str(report))


def test_each_run_writes_a_log_of_its_steps_and_model_calls(
    ingested: ChunkStore, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "TOP_K", 1)
    made_up = Citation(path="app/auth.py", start_line=90, end_line=95, symbol="LoginService")
    llm = ScriptedLLM(
        AgentAction(action="read", path="app/auth.py", start_line=10, end_line=15),
        answer(HASHED, Finding(claim="Made up.", citations=[made_up])),
        ReportDraft(answer="Hashed [1]."),
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, FIRST_HASHING))

    events = read_log(runs_dir / f"{report.run_id}.jsonl")
    assert [event.pop("event") for event in events] == [
        "start",
        "tool",
        "call",
        "step",
        "tool",
        "call",
        "step",
        "call",
        "end",
    ]
    assert all(isinstance(event.pop("time"), str) for event in events)
    start, search, call, read_step, read, _, answer_step, writer, end = events
    assert start == {
        "run_id": str(report.run_id),
        "snapshot": str(SNAPSHOT),
        "question": QUESTION,
        "model": "fake:scripted",
    }
    assert search == {
        "tool": "search_code",
        "args": {"query": QUESTION},
        "shown": ["app/auth.py:1-7 hash_password"],
    }
    assert call == {
        "model": "fake:scripted",
        "schema": "AgentAction",
        "input_tokens": 1000,
        "output_tokens": 100,
        "latency_s": 0.5,
    }
    assert read_step == {
        "step": 1,
        "action": "read",
        "args": {"path": "app/auth.py", "start_line": 10, "end_line": 15},
    }
    assert read["shown"] == ["app/auth.py:10-15 LoginService"]
    assert answer_step == {"step": 2, "action": "answer", "findings": 2}
    assert writer["schema"] == "ReportDraft"
    assert end["findings"] == 1
    assert end["rejected"] == ["app/auth.py:90-95 LoginService"]
    assert end["answer"] == "Hashed [1]."
    assert end["duration_s"] == report.duration_s


def test_a_failed_run_logs_its_calls_and_the_error(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(answer(HASHED))  # no answer to write

    with pytest.raises(AssertionError, match="no scripted answer"):
        run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    [log] = runs_dir.glob("*.jsonl")
    events = read_log(log)
    assert [event["event"] for event in events] == ["start", "tool", "call", "step", "error"]
    assert "no scripted answer for ReportDraft" in events[-1]["error"]


def test_the_report_keeps_the_rejected_citations(ingested: ChunkStore, runs_dir: Path) -> None:
    made_up = Citation(path="app/auth.py", start_line=90, end_line=95)
    uncited = Finding(claim="Passwords are stored in plain text.", citations=[])
    partly = Finding(claim=CHECKED.claim, citations=[LOGIN, made_up])
    llm = ScriptedLLM(answer(partly, uncited), ReportDraft(answer="[1]"))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.rejected == [made_up]
