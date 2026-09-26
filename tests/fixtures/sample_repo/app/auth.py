import hashlib

SALT = "pepper"


def hash_password(password: str) -> str:
    return hashlib.sha256((SALT + password).encode()).hexdigest()


class LoginService:
    def __init__(self, users: dict[str, str]) -> None:
        self.users = users

    def login(self, name: str, password: str) -> bool:
        return self.users.get(name) == hash_password(password)
