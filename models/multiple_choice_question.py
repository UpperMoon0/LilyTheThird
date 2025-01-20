from typing import List

from models.multiple_choice_answer import MultipleChoiceAnswer


class MultipleChoiceQuestion:
    def __init__(self, question: str, weight: int, answers: List[MultipleChoiceAnswer], category: str):
        self.question = question
        self.weight = weight
        self.answers = answers
        self.category = category