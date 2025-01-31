# discord_integration/commands/gtnh_test.py
import random
import discord
from discord.ui import View, Button

from discord_integration.commands.gtnh_test.gtnh_questions import questions
from models.multiple_choice_answer import MultipleChoiceAnswer


class GTNHIntelligenceTestCommand:
    def __init__(self, bot):
        self.bot = bot
        self.questions = questions  # Use the imported questions

        @self.bot.tree.command(name="gtnh_intelligence_test", description="Test your knowledge about the modpack GT: New Horizons.")
        async def gtnh_intelligence_test_command(interaction: discord.Interaction):
            """Asks a random set of questions and evaluates the user's score."""

            username = interaction.user.name
            user_score = {'score': 0}  # Store score in a mutable object (dictionary)

            # Randomly pick n questions
            n = 8  # Number of questions to ask
            selected_questions = random.sample(self.questions, n)

            # Shuffle the selected questions
            random.shuffle(selected_questions)

            # Calculate the total weight
            total_weight = sum(question.weight for question in selected_questions)

            # Start by sending the introduction message
            await interaction.response.send_message(f"Starting the GT: New Horizons Intelligence Test for {username}...")

            # Function to ask the next question
            async def ask_question(question_list, index):
                if index < len(question_list):
                    question = question_list[index]
                    question_content = question.question
                    question_weight = question.weight
                    view = View()

                    # Create buttons for the answers
                    for answer in question.answers:
                        button = Button(label=answer.answer, style=discord.ButtonStyle.primary, custom_id=answer.answer)
                        button.callback = self.create_button_callback(answer, question_weight, user_score, total_weight, question_list, index, ask_question, username)
                        view.add_item(button)

                    # Send the question to the user
                    await interaction.followup.send(content=question_content, view=view)

            # Start the quiz by asking the first question
            await ask_question(selected_questions, 0)  # Start with the first question

    # Callback function to handle answer button clicks
    def create_button_callback(self, answer: MultipleChoiceAnswer, question_weight: int, user_score: dict, total_weight: int, selected_questions, index, ask_question, username):
        async def button_callback(interaction: discord.Interaction):
            # Calculate the points earned for this question on a 100-point scale
            earned_points = (question_weight / total_weight) * 100

            # Check if the selected answer is correct
            if answer.correct:
                user_score['score'] += earned_points
                feedback = f"Correct! {username} earned {earned_points:.2f} points."
            else:
                feedback = f"Incorrect. {username} is kinda dumb..."

            # Send feedback
            await interaction.response.send_message(feedback)

            # Move to the next question
            next_index = index + 1
            if next_index < len(selected_questions):
                await ask_question(selected_questions, next_index)  # Ask the next question
            else:
                # Final message with score
                final_score = user_score['score']
                await interaction.followup.send(f"The test is over. {username}'s final score: {final_score:.2f} / 100.")

        return button_callback