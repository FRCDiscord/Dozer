"""Provides commands that pull information from First Q&A Form."""
import discord
import aiohttp

from ._utils import *
from bs4 import BeautifulSoup

from discord.ext import commands
from dozer.context import DozerContext
from discord import app_commands


class QA(commands.Cog):
    """QA commands"""

    def __init__(self, bot) -> None:
        self.ses = aiohttp.ClientSession()
        super().__init__()
        self.bot = bot

    @commands.hybrid_command(name="ftcqa", aliases=["ftcqaforum"], pass_context=True)
    @bot_has_permissions(embed_links = True)
    @app_commands.describe(question = "The number of the question you want to look up")
    async def ftcqa(self, ctx: DozerContext, question: int):
        """
        Shows Answers from the FTC Q&A
        """
        async with self.ses.get('https://ftc-qa.firstinspires.org/onepage.html') as response:
            html_data = await response.text()

        answers = BeautifulSoup(html_data, 'html.parser').get_text()

        start = answers.find('Q' + str(question) + ' ')
        a = ""
        if start > 0:

            finish = answers.find('answered', start) + 24
            a = answers[start:finish]

            # remove newlines
            a = a.replace("\n", " ")

            # remove multiple spaces
            a = " ".join(a.split())

            embed = discord.Embed(
                title = a[:a.find(" Q: ")],
                url = "https://ftc-qa.firstinspires.org/qa/" + str(question),
                color = discord.Color.blue())

            embed.add_field(name = "Question",
                            value = a[a.find(" Q: ") + 1:a.find(" A: ")],
                            inline = False)
            embed.add_field(name = "Answer",
                            value = a[a.find(" A: ") + 1:a.find(" ( Asked by ")],
                            inline = False)

            embed.set_footer(
                text = a[a.find(" ( Asked by ") + 1:])

            await ctx.send(embed = embed, ephemeral = True)

        else:
            a = "That question was not answered or does not exist."

            # add url
            a += "\nhttps://ftc-qa.firstinspires.org/qa/" + question
            await ctx.send(a, ephemeral = True)

    ftcqa.example_usage = """
    `{prefix}ftcqa 19` - show information on FTC Q&A #19
    """

    @commands.hybrid_command(name="frcqa", aliases=["frcqaforum"], pass_context=True)
    @bot_has_permissions(embed_links = True)
    @app_commands.describe(question = "The number of the question you want to look up")
    async def frcqa(self, ctx: DozerContext, question: int):
        """
        Shows Answers from the FRC Q&A
        """
        async with self.ses.get('https://frc-qa.firstinspires.org/onepage.html') as response:
            html_data = await response.text()

        answers = BeautifulSoup(html_data, 'html.parser').get_text()

        start = answers.find('Q' + str(question) + ' ')
        a = ""
        if start > 0:

            finish = answers.find('answered', start) + 24
            a = answers[start:finish]

            # remove newlines
            a = a.replace("\n", " ")

            # remove multiple spaces
            a = " ".join(a.split())

            embed = discord.Embed(
                title = a[:a.find(" Q: ")],
                url = "https://frc-qa.firstinspires.org/qa/" + str(question),
                color = discord.Color.blue())

            embed.add_field(name = "Question",
                            value = a[a.find(" Q: ") + 1:a.find(" A: ")],
                            inline = False)
            embed.add_field(name = "Answer",
                            value = a[a.find(" A: ") + 1:a.find(" ( Asked by ")],
                            inline = False)

            embed.set_footer(
                text = a[a.find(" ( Asked by ") + 1:])

            await ctx.send(embed = embed, ephemeral = True)

        else:
            a = "That question was not answered or does not exist."

            # add url
            a += "\nhttps://frc-qa.firstinspires.org/qa/" + question
            await ctx.send(a, ephemeral = True)

    frcqa.example_usage = """
    `{prefix}frcqa 19` - show information on FRC Q&A #19
    """

async def setup(bot):
    """Adds the QA cog to the bot."""
    await bot.add_cog(QA(bot))
