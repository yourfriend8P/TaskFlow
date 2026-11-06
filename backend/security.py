from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="bcrypt")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def verify_password_and_update(
    password: str,
    password_hash: str,
) -> tuple[bool, str | None]:
    return pwd_context.verify_and_update(password, password_hash)
