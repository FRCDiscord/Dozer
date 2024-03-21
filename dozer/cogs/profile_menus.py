"""Provides the ability to add commands to user profiles in servers"""
import discord
from discord.ext import commands
from discord import app_commands
from discord.utils import escape_markdown


from .. import db

embed_color = discord.Color(0xed791e)


class ProfileMenus(commands.Cog):
    """
    Creates a profile menu object for the bot
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.tree.add_command(profile)
        bot.tree.add_command(onteam)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(profile)
        self.bot.tree.remove_command(onteam)


class View_Profile(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(style = discord.ButtonStyle.blurple, label = "View Teams", custom_id = "onteam")
    async def onteam_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        self.stop()

@app_commands.context_menu(name = 'View Profile')
async def profile(interaction: discord.Interaction, member: discord.Member):
    """Creates the ephemeral response that will be sent to the user when they interact with the 'View Profile' button"""
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
    if len(teams) > 0:
        embed.add_field(name = f"On {len(teams)} team{'s' if len(teams) > 1 else ''}",
                        value = f"Click the button below to view the teams {member.mention} is on", inline = False)
        view = View_Profile()
        await interaction.response.send_message(embed = embed, view = view, ephemeral = True)
        await view.wait()
        if view.value:
            msg = await interaction.original_response()
            embed.remove_field(3 if member.premium_since is None else 4)
            await msg.edit(embed = embed, view = None)

            teams = await TeamNumbers.get_by(user_id = member.id)
            onteam_embed = discord.Embed(color = discord.Color.blue())
            onteam_embed.title = f'{member.display_name} is on the following team(s):'
            onteam_embed.description = "Teams: \n"
            for i in teams:
                onteam_embed.description = f"{onteam_embed.description} {i.team_type.upper()} Team {i.team_number} \n"
            if len(onteam_embed.description) > 4000:
                onteam_embed.description = onteam_embed.description[:4000] + "..."

            await interaction.followup.send(embed = onteam_embed, ephemeral = True)
    else:
        await interaction.response.send_message(embed = embed, ephemeral = True)

@app_commands.context_menu(name = 'Teams User is On')
async def onteam(interaction: discord.Interaction, user: discord.Member):
    """Creates the ephemeral response that will be sent to the user when they interact with the 'View Team' button"""
    teams = await TeamNumbers.get_by(user_id = user.id)

    if len(teams) == 0:
        await interaction.response.send_message("This user is not on any teams", ephemeral = True)
    else:
        embed = discord.Embed(color = discord.Color.blue())
        embed.title = f'{user.display_name} is on the following team(s):'
        embed.description = "Teams: \n"
        for i in teams:
            embed.description = f"{embed.description} {i.team_type.upper()} Team {i.team_number} \n"
        if len(embed.description) > 4000:
            embed.description = embed.description[:4000] + "..."
        await interaction.response.send_message(embed = embed, ephemeral = False)


async def setup(bot):
    """Adds the profile context menus cog to the bot."""
    await bot.add_cog(ProfileMenus(bot))


class TeamNumbers(db.DatabaseTable):
    """Database operations for tracking team associations."""
    __tablename__ = 'team_numbers'
    __uniques__ = ('user_id', 'team_number', 'team_type',)

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            user_id bigint NOT NULL,
            team_number text NOT NULL,
            team_type VARCHAR NOT NULL,
            PRIMARY KEY (user_id, team_number, team_type)
            )""")

    def __init__(self, user_id, team_number, team_type):
        super().__init__()
        self.user_id = user_id
        self.team_number = team_number
        self.team_type = team_type

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = TeamNumbers(user_id = result.get("user_id"),
                              team_number = result.get("team_number"),
                              team_type = result.get("team_type"))
            result_list.append(obj)
        return result_list
        
