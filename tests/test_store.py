import threading

from repolens.store import ChunkStore


def test_setup_can_run_in_two_processes_at_once(store: ChunkStore) -> None:
    errors: list[Exception] = []

    def setup() -> None:
        try:
            store.setup()
        except Exception as exc:
            errors.append(exc)

    for _ in range(5):  # the race doesn't show every time
        threads = [threading.Thread(target=setup) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert errors == []
