from textwrap import dedent

from repolens.chunking import Chunk, chunk_file


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
        ("<module>", 1, 3),
        ("connect", 6, 7),
        ("Session", 10, 15),
    ]
    assert chunks[1].path == "app/session.py"
    assert chunks[1].text == "def connect(url):\n    return os.environ.get(url)"


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
        ("<module>", 1, 1),
        ("User", 3, 5),
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
