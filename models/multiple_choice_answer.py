class MultipleChoiceAnswer:
    def __init__(self, answer: str, correct: bool = False):
        self.answer = answer
        self.correct = correct