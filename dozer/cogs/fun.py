"""Adds fun commands to the bot"""
import random
from asyncio import sleep

import discord
from discord.ext.commands import cooldown, BucketType, guild_only
from ._utils import *


class Fun(Cog):
    """Fun commands"""
    @guild_only()
    @cooldown(1, 20, BucketType.channel)
    @command()
    async def fight(self, ctx, opponent: discord.Member):
        """Start a fight with another user."""
        responses = [
            "was hit on the head by",
            "was kicked by",
            "was slammed into a wall by",
            "was dropkicked by",
            "was DDoSed by",
            "was chokeslammed by",
            "was run over with a robot by",
            "had their IQ dropped 15 points by",
            "had a heavy object dropped on them by",
            "was beat up by"
        ]

        damages = [100, 150, 200, 300, 50, 250, 420]
        players = [ctx.author, opponent]
        hps = [1000, 1000]
        turn = random.randint(0, 1)

        messages = []
        while hps[0] > 0 and hps[1] > 0:
            opp_idx = (turn + 1) % 2
            damage = random.choice(damages)
            if players[turn].id in ctx.bot.config['developers']:
                damage = damage * 2
            hps[opp_idx] = max(hps[opp_idx] - damage, 0)
            messages.append(
                await ctx.send("**{opponent}** {response} **{attacker}**! *[-{dmg} hp] [{hp} HP remaining]*".format(
                    opponent=players[opp_idx].name,
                    attacker=players[turn].name,
                    response=random.choice(responses),
                    dmg=damage,
                    hp=hps[opp_idx]
                )))
            await sleep(1.5)
            turn = opp_idx
        await ctx.send(
            "{loser} lost! GG {winner}!".format(loser=players[turn].mention, winner=players[(turn + 1) % 2].mention))
        await sleep(5)
        # bulk delete if we have the manage messages permission
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.channel.delete_messages(messages)
        else:
            # otherwise delete manually
            for msg in messages:
                await msg.delete()

    fight.example_usage = """
    `{prefix}fight @user2#2322 - Initiates a fight with @user2#2322`
    """


def setup(bot):
    """Adds the fun cog to Dozer"""
    bot.add_cog(Fun(bot))
