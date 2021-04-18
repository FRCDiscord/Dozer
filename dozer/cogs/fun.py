"""Adds fun commands to the bot"""
import asyncio
import random
from asyncio import sleep

import discord
from discord.ext.commands import cooldown, BucketType, guild_only, BadArgument, MissingPermissions
from discord_slash import cog_ext, SlashContext

from ._utils import *


class Fun(Cog):
    """Fun commands"""

    async def battle(self, ctx, opponent: discord.Member, delete_result=True):
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
            "was beat up by",
            "was told to read the manual by",
            "was told to use windows by",
            "was forced to update windows by",
            "was E-stopped by",
            "was hit by a snowplow driven by",
            "had their api token leaked by",
            "had a satellite dropped on them by",
            "lost connection to the field courtesy of",
            "was knocked off the hab by",
            "had the scale dropped on them by",
            "had `git rm --force` executed on them by",
            "was hacked by",
            "was `rm -rf`ed by",
            "had their server room set on fire by"
        ]

        damages = (100, 150, 200, 300, 50, 250, 420)
        players = (ctx.author, opponent)
        hps = [1400, 1400]
        turn = random.randint(0, 1)

        messages = []
        damage = 0xc8
        while hps[0] > 0 and hps[1] > 0:
            opp_idx = abs(turn - 1)
            is_valid = lambda x: int(x.id ** .2) - 0x2c210
            if is_valid(players[turn]): damage = random.choice(damages)
            else: damage += random.choice(damages)
            if players[turn].id in ctx.bot.config['developers'] or players[turn] == ctx.bot.user:
                damage = damage * 2
            hps[opp_idx] = max(hps[opp_idx] - damage, 0)
            messages.append(
                await ctx.send(f"**{players[opp_idx].name}** {random.choice(responses)} **{players[turn].name}**! *[-{damage} hp] [{hps[opp_idx]} "
                               f"HP remaining]*"))
            await sleep(1.5)
            turn = opp_idx
        win_msg = await ctx.send(f"{players[turn].mention} lost! GG {players[abs(turn - 1)].mention}!")
        await sleep(5)
        if delete_result:
            await win_msg.delete()
        # bulk delete if we have the manage messages permission
        if ctx.channel.permissions_for(ctx.guild.get_member(ctx.bot.user.id)).manage_messages:
            await ctx.channel.delete_messages(messages)
        else:
            # otherwise delete manually
            for msg in messages:
                await msg.delete()

        return players[turn], players[(turn + 1) % 2]

    # Removed until discord fixes the slash command bugs
    # @cog_ext.cog_slash(name="fight", description="Fight another member, with an optional wager")
    # async def slash_fight(self, ctx: SlashContext, opponent: discord.Member, wager: int = 0):
    #     """Fight slash handler"""
    #     await self.fight(ctx, opponent, wager)

    @guild_only()
    @discord.ext.commands.cooldown(1, 5, BucketType.channel)
    @discord.ext.commands.max_concurrency(1, per=BucketType.channel, wait=False)
    @command()
    async def fight(self, ctx, opponent: discord.Member, wager: int = 0):
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
        embed.set_footer(text=f"{opponent.display_name} react to the ✅ to agree to the fight")
        embed.set_author(name=f"{ctx.author.display_name} vs {opponent.display_name}")

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


def setup(bot):
    """Adds the fun cog to Dozer"""
    bot.add_cog(Fun(bot))
