"""Provides commands that pull information from First Q&A Form."""
from typing import Union
import re
import datetime
import json

import aiohttp
from bs4 import BeautifulSoup
import discord
from discord.ext import commands
from discord import app_commands

from dozer.context import DozerContext
from ._utils import *


async def data(ctx: DozerContext, level: str, question: int) -> Union[str, None]:
    """Returns QA Forum info for specified FTC/FRC"""
    if level.lower() == "ftc":
        async with ctx.cog.ses.get('https://ftc-qa.firstinspires.org/onepage.html') as response:
            html_data = await response.text()
        forum_url = "https://ftc-qa.firstinspires.org/qa/"
    elif level.lower() == "frc":
        async with ctx.cog.ses.get('https://frc-qa.firstinspires.org/onepage.html') as response:
            html_data = await response.text()
        forum_url = "https://frc-qa.firstinspires.org/qa/"
    else:
        return None

    answers = BeautifulSoup(html_data, 'html.parser').get_text()

    start = answers.find(f'Q{question} ')
    a = ""
    if start > 0:
        finish = answers.find('answered', start) + 24
        a = answers[start:finish]
        # remove newlines
        a = a.replace("\n", " ")
        # remove multiple spaces
        a = " ".join(a.split())
        embed = discord.Embed(
            title=a[:a.find(" Q: ")],
            url=forum_url + str(question),
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Question",
            value=a[a.find(" Q: ") + 1:a.find(" A: ")],
            inline=False
        )
        embed.add_field(
            name="Answer",
            value=a[a.find(" A: ") + 1:a.find(" ( Asked by ")],
            inline=False
        )
        embed.set_footer(text=a[a.find(" ( Asked by ") + 1:])
        return embed

    else:
        return f"That question was not answered or does not exist.\n{forum_url + str(question)}"

def createRuleEmbed(rulenumber, text): 
    """Returns an embed for a given rule number and text"""
    year = datetime.datetime.now().year 
    embed = discord.Embed(
        title=f"Rule {rulenumber}",
        url=f"https://rules-search.pages.dev/{year}/rule/{rulenumber}",
        color=discord.Color.blue()
    )
    
    truncated_text = "```\n" + ' '.join(text[:1016].splitlines()) + "```"
    return embed


class QA(commands.Cog):
    """QA commands"""

    def __init__(self, bot) -> None:
        self.ses = aiohttp.ClientSession()
        super().__init__()
        self.bot = bot

    @command(name="ftcqa", aliases=["ftcqaforum"], pass_context=True)
    @bot_has_permissions(embed_links=True)
    @app_commands.describe(question="The number of the question you want to look up")
    async def ftcqa(self, ctx: DozerContext, question: int):
        """
        Shows Answers from the FTC Q&A
        """
        result = await data(ctx, "ftc", question)
        if isinstance(result, discord.Embed):
            await ctx.send(embed=result)
        else:
            await ctx.send(result)

    ftcqa.example_usage = """
    `{prefix}ftcqa 19` - show information on FTC Q&A #19
    """

    @command(name = "frcqa", aliases = ["frcqaforum"], pass_context = True)
    @bot_has_permissions(embed_links = True)
    @app_commands.describe(question = "The number of the question you want to look up")
    async def frcqa(self, ctx: DozerContext, question: int):
        """
        Shows Answers from the FRC Q&A
        """
        result = await data(ctx, "frc", question)
        if isinstance(result, discord.Embed):
            await ctx.send(embed=result)
        else:
            await ctx.send(result)

    frcqa.example_usage = """
    `{prefix}frcqa 19` - show information on FRC Q&A #19
    """


    @command(name = "frcrule", pass_context = True)
    @bot_has_permissions(embed_links = True)
    @app_commands.describe(rule = "The rule number")
    async def frcrule(self, ctx: DozerContext, *, rule: str):
        """
        Shows rules from a rule number or search query
        """
        matches = re.match(r'^(?P<letter>[a-zA-Z])(?P<number>\d{3})$', rule)
        ephemeral = False

        embed = discord.Embed(
            title="Error",
            color=discord.Color.blue()
        )

        if matches is None:
            await ctx.defer()
            async with ctx.cog.ses.post('https://search.grahamsh.com/search',json={'query': rule}) as response:
                json_data = await response.content.read()
            json_parsed = json.loads(json_data)
            
            if "error" not in json_parsed:
                embeds = []
                page = 1
                for currRule in json_parsed["data"]:
                    currEmbed = createRuleEmbed(currRule["text"], currRule["textContent"])
                    currEmbed.set_footer(text=f"Page {page} of 5")
                    embeds.append(currEmbed)
                    
            await paginate(ctx, embeds)
            return
            
        else:  
            letter_part = matches.group('letter')
            number_part = matches.group('number')
            year = datetime.datetime.now().year 
            async with ctx.cog.ses.get(f'https://rules-search.pages.dev/api/rule?query={letter_part}{number_part}') as response:
                json_data = await response.content.read()
            
            json_parsed = json.loads(json_data)
            
            if "error" not in json_parsed:
                text = json_parsed["textContent"]
                embed = createRuleEmbed(letter_part.upper() + number_part, text)
                embed.set_image(url=f"https://imagen.frctools.com/rule/{letter_part.upper() + number_part}/image.png")
            else:
                ephemeral = True
                embed.add_field(
                    name="Error",
                    value="No such rule"
                )

        await ctx.send(embed=embed, ephemeral=ephemeral)
    frcrule.example_usage = """
    `{prefix}frcrule g301` - sends the summary and link to rule G301
    `{prefix}frcrule can i cross the line before teleop` - sends the summary and link to the rule matching the query

    """

async def setup(bot):
    """Adds the QA cog to the bot."""
    await bot.add_cog(QA(bot))
