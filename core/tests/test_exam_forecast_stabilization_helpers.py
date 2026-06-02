from django.test import TestCase


class ExamForecastStabilizationHelpersTests(TestCase):
    def test_shrink_recent_perf_small_weight_stays_near_mastery(self):
        from core.analytics import _shrink_recent_perf

        current_mastery = 50.0
        recent_perf = 100.0
        recent_weight = 1.0

        recent_adj = _shrink_recent_perf(
            current_mastery=current_mastery,
            recent_perf=recent_perf,
            recent_weight=recent_weight,
        )
        self.assertGreaterEqual(recent_adj, 50.0)
        self.assertLess(recent_adj, 60.0)

    def test_shrink_recent_perf_large_weight_moves_towards_recent(self):
        from core.analytics import _shrink_recent_perf

        current_mastery = 50.0
        recent_perf = 100.0
        recent_weight = 40.0

        recent_adj = _shrink_recent_perf(
            current_mastery=current_mastery,
            recent_perf=recent_perf,
            recent_weight=recent_weight,
        )
        self.assertGreater(recent_adj, 80.0)
        self.assertLessEqual(recent_adj, 100.0)

    def test_smooth_prediction_limits_daily_step(self):
        from core.analytics import _smooth_prediction

        prev_pred = 50.0
        raw_pred = 90.0

        pred = _smooth_prediction(prev_pred=prev_pred, raw_pred=raw_pred)
        self.assertLessEqual(pred, 56.0)
        self.assertGreaterEqual(pred, 50.0)
