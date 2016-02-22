try:
    from django.apps import AppConfig

    class EulfedoraAppConfig(AppConfig):
        name = 'eulfedora'

except ImportError:
    pass