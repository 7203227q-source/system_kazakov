from django.core.management import call_command
from django.test import TestCase


class TaskAIAnnotateCommandSmokeTests(TestCase):
    def test_command_exists(self):
        try:
            call_command("ai_annotate_tasks", "--help")
        except SystemExit:
            # argparse exits with 0 after printing help
            pass
