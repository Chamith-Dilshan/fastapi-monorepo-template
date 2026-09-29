from faker import Faker

_faker = Faker()


class PostFactory:
    """
    Generates realistic post-payloads.

    Usage:
        PostFactory.build()
        PostFactory.build(title="Custom Title", author_id=user_id)
    """

    @staticmethod
    def build(**overrides) -> dict:
        data = {
            "title": _faker.sentence(nb_words=6).rstrip("."),
            "content": _faker.paragraph(nb_sentences=4),
            "published": True,
        }
        data.update(overrides)
        return data
