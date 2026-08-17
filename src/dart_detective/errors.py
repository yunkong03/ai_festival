"""도메인 예외."""
from __future__ import annotations


class DartDetectiveError(Exception):
    """이 패키지의 모든 예외 최상위."""


class FutureLeakageError(DartDetectiveError):
    """simulation_date 이후 문서가 조사 결과에 섞였다.

    Prompt로 '미래를 보지 말라'고 적는 것과 별개로, Retriever/DB Query 계층에서
    반드시 차단되어야 한다. 이 예외가 뜬다는 것은 차단이 실패했다는 뜻이다.
    """

    def __init__(self, message: str, offending: list[dict] | None = None):
        super().__init__(message)
        self.offending = offending or []


class ReplayLockedError(DartDetectiveError):
    """Decision 확정 전에 Reality Replay를 호출했다."""


class CaseNotFoundError(DartDetectiveError):
    """존재하지 않는 case_id."""


class SessionNotFoundError(DartDetectiveError):
    """존재하지 않는 session_id."""


class InsufficientPointsError(DartDetectiveError):
    """조사 포인트 부족."""
