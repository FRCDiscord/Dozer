"""Adds fun commands to the bot"""
import random
import asyncio
from asyncio import sleep

import discord
from discord import app_commands
from discord.ext.commands import cooldown, BucketType, guild_only, BadArgument, MissingPermissions
from discord.ext import commands
from discord.utils import escape_markdown

from dozer.context import DozerContext
from ._utils import *

blurple = discord.Color.blurple()


class Fun(commands.Cog):
    """Fun commands"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def battle(self, ctx: DozerContext, opponent: discord.Member, delete_result: bool = True):
        """Start a fight with another user."""
        attacks = [
            # These were edited by FTC members to contain more FTC-related options
            "**{opponent}** was hit on the head by **{attacker}** ",
            "**{opponent}** was kicked by **{attacker}** ",
            "**{opponent}** was slammed into a wall by **{attacker}** ",
            "**{opponent}** was dropkicked by **{attacker}** ",
            "**{opponent}** was DDoSed by **{attacker}** ",
            "**{opponent}** was run over with a robot by **{attacker}** ",
            "**{opponent}** had their IQ dropped 15 points by **{attacker}**",
            "**{opponent}** had a heavy object dropped on them by **{attacker}**",
            "**{opponent}** was beat up by **{attacker}** ",
            "**{opponent}** was told to read the manual by **{attacker}** ",
            "**{opponent}** was told to use Android Studio by **{attacker}**",
            "**{opponent}** was told to use windows by **{attacker}**",
            "**{opponent}** was forced to update windows by **{attacker}**",
            "**{opponent}** was E-stopped by **{attacker}** ",
            "**{opponent}** was hit by a snowplow driven by **{attacker}**",
            "**{opponent}** had their api token leaked by **{attacker}**",
            "**{opponent}** had a satellite dropped on them by **{attacker}**",
            "**{opponent}** lost connection to the field courtesy of **{attacker}**",
            "**{opponent}** had the scale dropped on them by **{attacker}**",
            "**{opponent}** had `git rm --force` executed on them by **{attacker}**",
            # this and the following messages up to the next comment are custom by @transorsmth#7483
            "**{opponent}** had their autonomous broken by **{attacker}**",
            "**{opponent}** was voted out by **{attacker}**",
            "**{opponent}** was called sus by **{attacker}**",
            "**{opponent}** was hit with a power cell by **{attacker}**",
            "**{opponent}** had their main breaker pressed by **{attacker}**",
            "**{opponent}** had a conflicting autonomous with **{attacker}**",
            "**{opponent}** was hit with a stapler by **{attacker}**",
            "**{opponent}** was knocked off the traversal bar by **{attacker}**",
            "**{opponent}** had their battery fall out out thanks to **{attacker}**",
            "**{opponent}** had their season ended by **{attacker}**",
            "**{opponent}** had their control hub bricked by **{attacker}**",
            "**{opponent}** had their roborio bricked by **{attacker}**",
            # this and the following messages are thanks to J-Man from the CHS discord server, who expended their
            # creative powers on these statements.
            "**{opponent}** extended too far outside their field perimeter in front of **{attacker}**", #FTC
            "**{opponent}** extended too far outside their frame perimeter in front of **{attacker}**", #FRC
            "**{opponent}** lost a coffee-drinking competition against **{attacker}**",
            "**{opponent}** was a no-show against **{attacker}**",
            "**{opponent}** fell asleep before a match against **{attacker}**",
            "**{opponent}** yelled ROBOT! too loudly at **{attacker}**",
            "**{opponent}** got caught running in the pits by **{attacker}**",
            "**{opponent}** had their robot disabled by **{attacker}**",
            "**{opponent}** got a red card from **{attacker}**",
            "**{opponent}** got a yellow card from **{attacker}**",
            "**{opponent}** failed their robot's inspection by **{attacker}**",
            "**{opponent}** had their drill battery stolen by **{attacker}**",
            "**{opponent}** had their firewall re-enabled by **{attacker}**",
            "**{opponent}** had their website hacked by **{attacker}**",
            "**{opponent}** got their head zipped in a power cube by **{attacker}**",
            "**{opponent}** lost their sponsorship to **{attacker}**",
            "**{opponent}** took an arrow in the knee from **{attacker}**",
            "**{opponent}** was given a tech foul by **{attacker}**",
            "**{opponent}** had their code corrupted by **{attacker}**",
            "**{opponent}** was found without adequate eye protection by **{attacker}**",
        ]

        damages = [50, 69, 100, 150, 200, 250, 300, 420]
        players = [ctx.author, opponent]
        hps = [1500, 1500]
        turn = random.randint(0, 1)

        messages = []
        while hps[0] > 0 and hps[1] > 0:
            opp_idx = (turn + 1) % 2
            damage = random.choice(damages)
            if players[turn].id in ctx.bot.config['developers'] or players[turn] == ctx.bot.user or players[turn].id == 675726066018680861:
                damage = damage * 1.5 #reduce amount of damage done by bot, devs(both in config and hardcoded)
            hps[opp_idx] = max(hps[opp_idx] - damage, 0)
            messages.append(
                await ctx.send(
                    f"{random.choice(attacks).format(opponent = players[opp_idx].name, attacker = players[turn].name)} *[-{damage} hp]"
                    f" [{hps[opp_idx]} HP remaining]*"))
            await sleep(1.5)
            turn = opp_idx
        win_embed = discord.Embed(description = f"{players[(turn + 1) % 2].mention} won! GG {players[turn].mention}!",
                                  color = blurple)
        await ctx.send(embed = win_embed)
        await sleep(5)
        # bulk delete if we have the manage messages permission
        if ctx.channel.permissions_for(ctx.guild.get_member(ctx.bot.user.id)).manage_messages:
            await ctx.channel.delete_messages(messages)
        else:
            # otherwise delete manually
            for msg in messages:
                await msg.delete()

        return players[turn], players[(turn + 1) % 2]

    @guild_only()
    @discord.ext.commands.cooldown(1, 5, BucketType.channel)
    @discord.ext.commands.max_concurrency(1, per=BucketType.channel, wait=False)
    @commands.command()
    async def fight(self, ctx: DozerContext, opponent: discord.Member, wager: int = 0):
        """Start a fight with another user."""

        levels = self.bot.get_cog("Levels")

        if wager == 0:
            await self.battle(ctx, opponent, delete_result=False)
            return

        levels_settings = levels.guild_settings.get(ctx.guild.id)
        if levels_settings is None or not levels_settings.enabled:
            raise BadArgument("Levels must be enabled to fight with xp wagers")

        if wager < 0:
            raise BadArgument("Wagers cannot be a negative amount")

        if ctx.author == opponent:
            raise BadArgument("You cannot fight yourself")

        if opponent.bot:
            raise BadArgument("You cannot wager against a bot")

        author_levels = await levels.load_member(ctx.guild.id, ctx.author.id)
        opponent_levels = await levels.load_member(ctx.guild.id, opponent.id)

        if author_levels.total_xp < wager:
            raise BadArgument("You not have enough XP to fulfill the wager")

        if opponent_levels.total_xp < wager:
            raise BadArgument(f"{opponent} does not have enough XP to fulfill the wager")

        embed = discord.Embed(description=f"{ctx.author.mention} has challenged {opponent.mention} to a fight with a wager of"
                                          f" {wager}xp")
        embed.set_footer(text=f"{escape_markdown(opponent.display_name)} react to the ✅ to agree to the fight")
        embed.set_author(name=f"{escape_markdown(ctx.author.display_name)} vs {escape_markdown(opponent.display_name)}")

        msg = await ctx.send(embed=embed)
        try:
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
        except discord.Forbidden:
            raise MissingPermissions(f"**{ctx.bot.user}** does not have the permission to add reacts")
        try:
            emoji = None

            def reaction_check(reaction, reactor):
                if (reaction.emoji == "✅" or reaction.emoji == "❌") and reactor == opponent and reaction.message == msg:
                    nonlocal emoji
                    emoji = reaction.emoji
                    return True
                else:
                    return False

            await self.bot.wait_for('reaction_add', timeout=45, check=reaction_check)

            if emoji == "✅":
                embed.set_footer(text="")  # Edit embed to show that fight is in progress
                embed.colour = 0xffff00
                try:
                    await msg.clear_reactions()
                except discord.Forbidden:
                    pass
                await msg.edit(content=None, embed=embed)

                looser, winner = await self.battle(ctx, opponent)
                embed.colour = 0x00ff00

                author_levels.total_xp += wager if winner is ctx.author else -wager
                opponent_levels.total_xp += wager if winner is opponent else -wager

                embed.add_field(name="Results", value=f"{winner.mention} beat {looser.mention}"
                                                      f"\n{ctx.author.mention} now is at "
                                                      f"level {levels.level_for_total_xp(author_levels.total_xp)} ({author_levels.total_xp} XP) "
                                                      f"\n{opponent.mention} now is at "
                                                      f"level {levels.level_for_total_xp(opponent_levels.total_xp)} ({opponent_levels.total_xp} XP)")

                levels.sync_member(ctx.guild.id, ctx.author.id)
                levels.sync_member(ctx.guild.id, opponent.id)

            elif emoji == "❌":
                try:
                    await msg.clear_reactions()
                except discord.Forbidden:
                    pass
                embed.add_field(name="Results", value=f"{opponent.mention} declined the fight, fight canceled")
                embed.set_footer(text="")
                embed.colour = 0xff0000

        except asyncio.TimeoutError:
            try:
                await msg.clear_reactions()
            except discord.Forbidden:
                pass
            embed.add_field(name="Results", value=f"{opponent.mention} failed to accept in time, fight canceled")
            embed.set_footer(text="")
            embed.colour = 0xff0000

        await msg.edit(content=None, embed=embed)

    fight.example_usage = """
        `{prefix}fight @user2#2322 - Initiates a fight with @user2#2322
         {prefix}fight @Snowplow#5196 670 - Initiates a fight with @Snowplow#5196 with a wager of 670xp`
        """

    
async def setup(bot):
    """Adds the fun cog to Dozer"""
    await bot.add_cog(Fun(bot))
