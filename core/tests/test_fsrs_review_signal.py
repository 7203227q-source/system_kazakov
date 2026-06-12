from django.test import SimpleTestCase

from core.services import determine_fsrs_signal


class FSRSReviewSignalTests(SimpleTestCase):
    def test_wrong_answer_maps_to_again(self):
        signal = determine_fsrs_signal(
            is_correct=False,
            active_time_seconds=20,
            attempt_count=1,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "again")

    def test_correct_answer_after_multiple_attempts_maps_to_hard(self):
        signal = determine_fsrs_signal(
            is_correct=True,
            active_time_seconds=40,
            attempt_count=2,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "hard")

    def test_correct_but_slow_answer_maps_to_hard(self):
        signal = determine_fsrs_signal(
            is_correct=True,
            active_time_seconds=140,
            attempt_count=1,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "hard")

    def test_correct_normal_speed_first_attempt_maps_to_good(self):
        signal = determine_fsrs_signal(
            is_correct=True,
            active_time_seconds=55,
            attempt_count=1,
            expected_time_seconds=60,
        )
        self.assertEqual(signal, "good")
