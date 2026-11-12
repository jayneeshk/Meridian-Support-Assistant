"""Capstone R6 - resilience patterns."""
from __future__ import annotations
import time


class CircuitBreaker:
    def __init__(self, failure_threshold=3, reset_after_s=30.0, clock=time.monotonic):
        self.failure_threshold = failure_threshold
        self.reset_after_s = reset_after_s
        self.clock = clock
        self.state = "closed"
        self.consecutive_failures = 0
        self.opened_at = self.clock()
        self._half_open_trial = False

    def allow(self):
        now = self.clock()
        if self.state == "closed":
            return True
        if self.state == "open":
            if now - self.opened_at >= self.reset_after_s:
                self.state = "half_open"
                self._half_open_trial = True
                return True
            return False
        if self.state == "half_open":
            if self._half_open_trial:
                self._half_open_trial = False
                return True
            return False
        return False

    def record_success(self):
        self.consecutive_failures = 0
        self.state = "closed"
        self._half_open_trial = False

    def record_failure(self):
        self.consecutive_failures += 1
        if self.state == "half_open":
            self.state = "open"
            self.opened_at = self.clock()
            self.consecutive_failures = self.failure_threshold
            return
        if self.consecutive_failures >= self.failure_threshold:
            self.state = "open"
            self.opened_at = self.clock()


def call_with_resilience(fn, *, retries=3, base_delay=0.1, max_delay=2.0, timeout_budget_s=5.0, fallback=None, breaker=None,
                         sleep=time.sleep, clock=time.monotonic, retry_on=(Exception,)):
    start = clock()
    attempts = 0
    last_error = None
    used_fallback = False

    def _result(value, ok, error, attempts_done, used_fallback_value=False):
        return {"ok": ok, "value": value, "attempts": attempts_done, "error": error, "used_fallback": used_fallback_value, "elapsed_s": clock() - start}

    if breaker is not None and not breaker.allow():
        err = {"type": "CircuitOpen", "message": "circuit open"}
        if fallback is not None:
            try:
                value = fallback()
                return _result(value, True, err, 0, True)
            except Exception:
                return _result(None, False, err, 0, False)
        return _result(None, False, err, 0, False)

    for attempt in range(1, retries + 2):
        attempts = attempt
        try:
            if breaker is not None and not breaker.allow():
                raise RuntimeError("CircuitOpen")
            value = fn()
            if breaker is not None:
                breaker.record_success()
            return _result(value, True, None, attempts, False)
        except Exception as exc:
            if breaker is not None:
                breaker.record_failure()
            exc_type = type(exc).__name__
            last_error = {"type": exc_type, "message": str(exc)}
            if not isinstance(exc, retry_on):
                if fallback is not None:
                    try:
                        value = fallback()
                        return _result(value, True, last_error, attempts, True)
                    except Exception:
                        return _result(None, False, last_error, attempts, False)
                return _result(None, False, last_error, attempts, False)
            if attempt > retries:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if clock() - start + delay > timeout_budget_s:
                last_error = {"type": "TimeoutBudgetExceeded", "message": f"retry budget exceeded after {attempt} attempts"}
                if fallback is not None:
                    try:
                        value = fallback()
                        return _result(value, True, last_error, attempts, True)
                    except Exception:
                        return _result(None, False, last_error, attempts, False)
                return _result(None, False, last_error, attempts, False)
            sleep(delay)
    if fallback is not None:
        try:
            value = fallback()
            return _result(value, True, last_error, attempts, True)
        except Exception:
            return _result(None, False, last_error, attempts, False)
    return _result(None, False, last_error, attempts, False)
