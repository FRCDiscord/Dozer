"""Provides the ability to add commands to user profiles in servers"""
import discord
from discord.ext import commands
from discord import app_commands


class ProfileMenus(commands.Cog):
    """
    Creates a profile menu object for the bot
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name = 'View Profile',
            callback = self.profile,  # sets the callback the view_profile function
        )
        self.bot.tree.add_command(self.ctx_menu)  # add the context menu to the tree

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type = self.ctx_menu.type)

    async def profile(self, interaction: discord.Interaction, member: discord.Member):
        """Creates the ephemeral response that will be sent to the user when they interact with the 'View Profile' button"""
        # await interaction.response.send_message(f'{member} joined at {discord.utils.format_dt(member.joined_at)}',
        # ephemeral = False)  # temp false for testing
        if member is None:
            member = interaction.user

        icon_url = member.avatar.replace(static_format = 'png', size = 32) or None

        embed = discord.Embed(title = member.display_name, description = f'{member!s} ({member.id}) | {member.mention}',
                              color = member.color)
        embed.add_field(name = 'Bot Created' if member.bot else 'Account Created',
                        value = discord.utils.format_dt(member.created_at), inline = True)
        embed.add_field(name = 'Member Joined', value = discord.utils.format_dt(member.joined_at), inline = True)
        if member.premium_since is not None:
            embed.add_field(name = 'Member Boosted', value = discord.utils.format_dt(member.premium_since),
                            inline = True)
        if len(member.roles) > 1:
            role_string = ' '.join([r.mention for r in member.roles][1:])
        else:
            role_string = member.roles[0].mention
        s = "s" if len(member.roles) >= 2 else ""
        embed.add_field(name = f"Role{s}: ", value = role_string, inline = False)
        embed.set_thumbnail(url = icon_url)
        await interaction.response.send_message(embed = embed, ephemeral = True)


async def setup(bot):
    """Adds the profile context menus cog to the bot."""
    await bot.add_cog(ProfileMenus(bot))
