from faker import Faker

_faker = Faker()

# A fixed strong password used as the default so tests can log in
_DEFAULT_PASSWORD = "StrongP@ssw0rd!"


class UserFactory:
    """
    Generates realistic user payloads.

    Usage:
        UserFactory.build()
        UserFactory.build(email="custom@example.com")
    """

    @staticmethod
    def build(**overrides) -> dict:
        data = {
            "email": _faker.unique.email(),
            "first_name": _faker.first_name(),
            "last_name": _faker.last_name(),
            "password": _DEFAULT_PASSWORD,
        }
        data.update(overrides)
        return data
