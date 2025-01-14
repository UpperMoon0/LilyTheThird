from typing import List

from models.multiple_choice_answer import MultipleChoiceAnswer


class MultipleChoiceQuestion:
    def __init__(self, question: str, weight: int, answers: List[MultipleChoiceAnswer]):
        self.question = question
        self.weight = weight
        self.answers = answers