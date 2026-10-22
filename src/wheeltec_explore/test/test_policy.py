import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from wheeltec_explore.policy import RetryBook, completion_state, observation_fresh
except ImportError:
    RetryBook = completion_state = observation_fresh = None

class ExplorationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(RetryBook, 'Exploration task policy is not implemented')
    def test_blacklist_expires_but_retry_limit_remains(self):
        book = RetryBook(cooldown=10, max_attempts=2)
        book.failed((1., 2.), now=0)
        self.assertFalse(book.available((1.1, 2.), now=5))
        self.assertTrue(book.available((1., 2.), now=11))
        book.failed((1.1, 2.), now=12)
        self.assertFalse(book.available((1., 2.), now=50))
    def test_completed_requires_map_return_and_sufficient_observation(self):
        self.assertEqual(completion_state(15, 0, 0, True, True), 'completed')
        self.assertEqual(completion_state(15, 0, 0, False, True), 'failed')
        self.assertEqual(completion_state(15, 0, 0, True, False), 'failed')
        self.assertEqual(completion_state(2, 0, 0, True, True), 'incomplete')
        self.assertEqual(completion_state(15, 1, 0, True, True), 'incomplete')
        self.assertEqual(completion_state(15, 0, 1, True, True), 'incomplete')

    def test_missing_or_stale_scans_cannot_support_exploration(self):
        self.assertFalse(observation_fresh(None, now=10))
        self.assertFalse(observation_fresh(1, now=10))
        self.assertTrue(observation_fresh(8, now=10))

if __name__ == '__main__': unittest.main()