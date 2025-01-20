from models.multiple_choice_answer import MultipleChoiceAnswer
from models.multiple_choice_question import MultipleChoiceQuestion

questions = [
    MultipleChoiceQuestion(
        "How many pieces of wool do you need to craft a bed before the Stone Age?",
        10,
        [MultipleChoiceAnswer("3", False),
         MultipleChoiceAnswer("4", False),
         MultipleChoiceAnswer("6", True),
         MultipleChoiceAnswer("8", False)],
        "Pre-Stone Age"
    ),
    MultipleChoiceQuestion(
        "Which creature explodes when killed with a sword?",
        15,
        [MultipleChoiceAnswer("Cow", True),
         MultipleChoiceAnswer("Chicken", False),
         MultipleChoiceAnswer("Pig", False),
         MultipleChoiceAnswer("Zombie", False)],
        "Pre-Stone Age"
    ),
    MultipleChoiceQuestion(
        "Which of these items/blocks doesn't need flint to craft?",
        15,
        [MultipleChoiceAnswer("Crafting Table", False),
         MultipleChoiceAnswer("Bed", True),
         MultipleChoiceAnswer("Furnace", False),
         MultipleChoiceAnswer("Chest", False),
         MultipleChoiceAnswer("All of them", False)],
        "Pre-Stone Age"
    ),
    MultipleChoiceQuestion(
        "In the early game, you can eat the same food repeatedly without any penalty.",
        20,
        [MultipleChoiceAnswer("True", False),
         MultipleChoiceAnswer("False", True)],
        "Pre-Stone Age"
    ),
    MultipleChoiceQuestion(
        "What wild fruit can you harvest in the early game?",
        15,
        [MultipleChoiceAnswer("Curry Leaf", False),
            MultipleChoiceAnswer("Rape (Canola)", False),
            MultipleChoiceAnswer("Blackberry", True),
            MultipleChoiceAnswer("UUA Berry", False)],
        "Pre-Stone Age"
    ),
    MultipleChoiceQuestion(
        "Which of these items can't you craft in the Stone Age?",
        20,
        [MultipleChoiceAnswer("Iron Chest", False),
            MultipleChoiceAnswer("(Coal) Coke", False),
            MultipleChoiceAnswer("Flint and Steel", True),
            MultipleChoiceAnswer("Smeltery Controller", False)],
        "Stone Age"
    ),
    MultipleChoiceQuestion(
        "How can you make charcoal in the Stone Age?",
        20,
        [MultipleChoiceAnswer("Pyrolyze Oven", False),
            MultipleChoiceAnswer("Furnace", False),
            MultipleChoiceAnswer("Smeltery", False),
            MultipleChoiceAnswer("Coke Oven", True)],
        "Stone Age"
    ),
    MultipleChoiceQuestion(
        "How can you make parts like plates, rods, screws, etc. in the Stone Age?",
        20,
        [MultipleChoiceAnswer("Gregtech tools: hammer, file, etc.", True),
            MultipleChoiceAnswer("Chisel", False),
            MultipleChoiceAnswer("Lathe", False),
            MultipleChoiceAnswer("Smeltery", False)],
        "Stone Age"
    ),
    MultipleChoiceQuestion(
        "How can you turn ingots into tool parts in the Stone Age?",
        20,
        [MultipleChoiceAnswer("Crafting Table", False),
         MultipleChoiceAnswer("Smeltery", True),
         MultipleChoiceAnswer("Furnace", False),
         MultipleChoiceAnswer("Anvil", False)],
        "Stone Age"
    ),
    MultipleChoiceQuestion(
        "How many items a bucket of creosote oil can smelt in the furnace?",
        10,
        [MultipleChoiceAnswer("8", False),
         MultipleChoiceAnswer("64", False),
         MultipleChoiceAnswer("16", False),
            MultipleChoiceAnswer("32", True)],
        "Stone Age"
    ),
    MultipleChoiceQuestion(
        "You can get steel before the Steam Age.",
        20,
        [MultipleChoiceAnswer("True", True),
         MultipleChoiceAnswer("False", False)],
        "Steam Age"
    ),
]