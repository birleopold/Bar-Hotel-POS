from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    label = "common"
    verbose_name = "Common"

    def ready(self) -> None:
        from apps.common.json_logging import configure_warnings_stream

        configure_warnings_stream()
