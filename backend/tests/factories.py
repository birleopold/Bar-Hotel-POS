import factory
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        if not create:
            return
        raw = extracted if extracted is not None else "testpass123"
        obj.set_password(raw)
        obj.save(update_fields=["password"])
