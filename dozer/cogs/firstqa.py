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


def html_to_text(html: str) -> str:
    """Converts the HTML used for questions and answers to plain text"""
    soup = BeautifulSoup(html, 'html.parser')
    for item in soup.find_all("li"):
        item.insert_before("\n- ")
    for item in soup.find_all(["p", "br", "ol", "ul"]):
        item.insert_after("\n")
    lines = (" ".join(line.split()) for line in soup.get_text().split("\n"))
    return "\n".join(line for line in lines if line).strip()


def add_chunked_field(embed: discord.Embed, name: str, text: str) -> None:
    """Adds text to an embed, splitting it across fields to respect the 1024 character limit"""
    for i in range(0, max(len(text), 1), 1024):
        embed.add_field(name=name if i == 0 else "\u200b", value=text[i:i + 1024] or "\u200b", inline=False)


async def data(ctx: DozerContext, level: str, question: int) -> Union[discord.Embed, str, None]:
    """Returns QA Forum info for specified FTC/FRC"""
    level = level.lower()
    if level not in ("ftc", "frc"):
        return None

    year = ftc_season_year() if level == "ftc" else datetime.datetime.now().year
    board_url = f"https://game-qa.firstinspires.org/boards/{year}/{level.upper()}/QA"
    # boards that don't exist yet redirect to a login page instead of returning an error
    async with ctx.cog.ses.get(f"{board_url}/questions", allow_redirects=False) as response:
        if response.status != 200:
            return f"The {level.upper()} {year} Q&A board is not available.\n{board_url}"
        questions = await response.json()

    match = next((q for q in questions if q["number"] == question), None)
    if match is None or match.get("answer") is None:
        return f"That question was not answered or does not exist.\n{board_url}"

    embed = discord.Embed(
        title=f"Q{question}: {match['title']}"[:256],
        url=f"{board_url}/qa/{question}",
        color=discord.Color.blue()
    )
    add_chunked_field(embed, "Question", html_to_text(match["content"]))
    add_chunked_field(embed, "Answer", html_to_text(match["answer"]["content"]))
    details = [f"{label}: {match[key]}" for label, key in (("Rule", "rule"), ("Topic", "topic")) if match.get(key)]
    answered = datetime.datetime.fromtimestamp(match["answer"]["createdAt"] / 1000, datetime.timezone.utc)
    details.append(f"Answered {answered:%Y-%m-%d}")
    embed.set_footer(text=" | ".join(details))
    return embed

def ftc_season_year() -> int:
    """Returns the year the current FTC season ends in; seasons run September to May"""
    now = datetime.datetime.now()
    return now.year + 1 if now.month >= 9 else now.year


def createRuleEmbed(rulenumber):
    """Returns an embed for a given rule number and text"""
    year = datetime.datetime.now().year 
    embed = discord.Embed(
        title=f"Rule {rulenumber}",
        url=f"https://frctools.com/{year}/rule/{rulenumber}",
        color=discord.Color.blue()
    )
    
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
            async with ctx.cog.ses.get(f'https://frctools.com/api/search?query={rule}') as response:
                json_data = await response.content.read()
            json_parsed = json.loads(json_data)
            
            if "error" not in json_parsed:
                embeds = []
                page = 1
                for currRule in json_parsed["hits"]:
                    currEmbed = createRuleEmbed(currRule["name"])
                    currEmbed.set_image(url=f"https://imagen.frctools.com/rule/{currRule['name']}/image.png")
                    currEmbed.set_footer(text=f"Page {page} of {len(json_parsed)}")
                    embeds.append(currEmbed)
                    page += 1
                    
            await paginate(ctx, embeds)
            return
            
        else:  
            letter_part = matches.group('letter')
            number_part = matches.group('number')
            year = datetime.datetime.now().year 
            async with ctx.cog.ses.get(f'https://frctools.com/api/rule?query={letter_part}{number_part}') as response:
                json_data = await response.content.read()
            
            json_parsed = json.loads(json_data)
            
            if "error" not in json_parsed:
                text = json_parsed["textContent"]
                embed = createRuleEmbed(letter_part.upper() + number_part)
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
