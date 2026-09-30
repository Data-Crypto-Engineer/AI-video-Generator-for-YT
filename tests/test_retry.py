import unittest
from utils.retry import retry_with_backoff, PermanentPipelineError, TransientPipelineError

class TestRetry(unittest.TestCase):
    def test_permanent_error_not_retried(self):
        attempts = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def failing_func():
            nonlocal attempts
            attempts += 1
            raise PermanentPipelineError("Invalid API key")

        with self.assertRaises(PermanentPipelineError):
            failing_func()

        self.assertEqual(attempts, 1)

    def test_transient_error_retries_and_succeeds(self):
        attempts = 0

        @retry_with_backoff(max_retries=3, initial_delay=0.01, retry_on=(TransientPipelineError,))
        def flaky_func():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TransientPipelineError("Temporary 503")
            return "success"

        result = flaky_func()
        self.assertEqual(result, "success")
        self.assertEqual(attempts, 3)

if __name__ == "__main__":
    unittest.main()
