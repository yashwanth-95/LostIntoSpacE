"""Runs a question set against the assistant."""

import asyncio
from typing import Any, List, Optional, Sequence

from ..datasets.rag_questions import RAG_QUESTIONS, RAGQuestion
from ..metrics.grounding import AnswerOutcome, GroundingSummary, score_answer, summarize

__all__ = ["run_rag_evaluation", "run_rag_evaluation_sync"]


async def run_rag_evaluation(
    assistant: Any, questions: Optional[Sequence[RAGQuestion]] = None
) -> GroundingSummary:
    """Ask every question and score the answers.

    A question that raises is recorded as a failed outcome rather than
    aborting the run — one broken case must not hide the other thirty-nine.
    """
    items = list(questions if questions is not None else RAG_QUESTIONS)
    outcomes: List[AnswerOutcome] = []

    for question in items:
        try:
            response = await assistant.ask(question.question)
        except Exception as exc:  # noqa: BLE001 - a crash is a result, not a stop
            outcomes.append(
                AnswerOutcome(
                    question_id=question.id,
                    question=question.question,
                    should_decline=question.should_decline,
                    declined=False,
                    notes=["raised {0}: {1}".format(exc.__class__.__name__, exc)],
                )
            )
            continue
        outcomes.append(score_answer(question, response))

    return summarize(outcomes)


def run_rag_evaluation_sync(
    assistant: Any, questions: Optional[Sequence[RAGQuestion]] = None
) -> GroundingSummary:
    """Synchronous wrapper, for scripts and report generation."""
    return asyncio.get_event_loop().run_until_complete(
        run_rag_evaluation(assistant, questions)
    )
