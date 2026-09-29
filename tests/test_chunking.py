from textwrap import dedent

from repolens.chunking import MAX_CHUNK_LINES, Chunk, chunk_file


def spans(chunks: list[Chunk]) -> list[tuple[str, int, int]]:
    return [(chunk.symbol, chunk.start_line, chunk.end_line) for chunk in chunks]


def test_python_file_is_split_at_function_and_class_boundaries() -> None:
    source = dedent(
        """\
        import os

        TIMEOUT = 3


        def connect(url):
            return os.environ.get(url)


        @dataclass
        class Session:
            token: str

            def refresh(self):
                return self.token
        """
    )

    chunks = chunk_file("app/session.py", source)

    assert spans(chunks) == [
        ("connect", 1, 7),  # with the short module code before it
        ("Session", 10, 15),
    ]
    assert chunks[0].path == "app/session.py"
    assert chunks[0].text.endswith("\n\ndef connect(url):\n    return os.environ.get(url)")


def function(name: str, body_lines: int, indent: str = "") -> str:
    body = "".join(f"{indent}    x = {i}\n" for i in range(body_lines - 1))
    return f"{indent}def {name}(self):\n{body}"


def test_oversized_class_is_split_into_methods() -> None:
    source = (
        "class Store:\n"
        '    """Keeps things."""\n'
        "\n" + function("load", 80, indent="    ") + "\n" + function("save", 80, indent="    ")
    )

    chunks = chunk_file("store.py", source)

    assert spans(chunks) == [
        ("Store", 1, 2),
        ("Store.load", 4, 83),
        ("Store.save", 85, 164),
    ]


def test_oversized_function_is_cut_into_windows() -> None:
    chunks = chunk_file("long.py", function("handle", 400))

    assert spans(chunks) == [
        ("handle", 1, 150),
        ("handle", 151, 300),
        ("handle", 301, 400),
    ]


def test_short_module_code_joins_the_definition_next_to_it() -> None:
    source = dedent(
        """\
        import typer

        app = typer.Typer()


        @app.command()
        def main(name: str):
            print(f"Hello {name}")


        if __name__ == "__main__":
            app()
        """
    )

    assert spans(chunk_file("tutorial.py", source)) == [("main", 1, 12)]


def test_long_module_code_keeps_its_own_chunk() -> None:
    constants = "".join(f"X{i} = {i}\n" for i in range(10))

    chunks = chunk_file("settings.py", constants + "\n\n" + function("load", 3))

    assert spans(chunks) == [("<module>", 1, 10), ("load", 13, 15)]


def test_module_code_stays_apart_from_a_definition_it_would_make_too_long() -> None:
    source = "import os\n\n\n" + function("handle", MAX_CHUNK_LINES - 1) + "\n\nmain()\n"

    assert spans(chunk_file("long.py", source)) == [
        ("<module>", 1, 1),
        ("handle", 4, MAX_CHUNK_LINES + 2),
        ("<module>", MAX_CHUNK_LINES + 5, MAX_CHUNK_LINES + 5),
    ]


def test_typescript_file_is_split_at_declarations() -> None:
    source = dedent(
        """\
        import { db } from "./db";

        export interface User {
          id: string;
        }

        export type Role = "admin" | "member";

        export const findUser = async (id: string) => {
          return db.get(id);
        };

        export default class UserService {
          list() {
            return db.all();
          }
        }

        function helper() {}
        """
    )

    chunks = chunk_file("src/users.ts", source)

    assert spans(chunks) == [
        ("User", 1, 5),
        ("Role", 7, 7),
        ("findUser", 9, 11),
        ("UserService", 13, 17),
        ("helper", 19, 19),
    ]


def test_tsx_components_are_chunked() -> None:
    source = dedent(
        """\
        export function Greeting({ name }: { name: string }) {
          return <p>Hello {name}</p>;
        }
        """
    )

    assert spans(chunk_file("src/Greeting.tsx", source)) == [("Greeting", 1, 3)]
