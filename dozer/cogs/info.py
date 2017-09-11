import discord, unicodedata
from discord.ext.commands import guild_only
from ._utils import *

blurple = discord.Color.blurple()
datetime_format = '%Y-%m-%d %I:%M %p'

class Info(Cog):
	@guild_only()
	@command(aliases=['user', 'userinfo', 'memberinfo'])
	async def member(self, ctx, member : discord.Member = None):
		"""Retrieve information about a member of the guild."""
		async with ctx.typing():
			member = member or ctx.author
			icon_url = member.avatar_url_as(static_format='png')
			e = discord.Embed(color=member.color)
			e.set_thumbnail(url=icon_url)
			e.add_field(name='Name', value=str(member))
			e.add_field(name='ID', value=member.id)
			e.add_field(name='Nickname', value=member.nick, inline=member.nick is None)
			e.add_field(name='Bot Created' if member.bot else 'User Joined Discord', value=member.created_at.strftime(datetime_format))
			e.add_field(name='Joined Guild', value=member.joined_at.strftime(datetime_format))
			e.add_field(name='Color', value=str(member.color).upper())
			
			e.add_field(name='Status and Game', value='%s, playing %s' % (str(member.status).title(), member.game), inline=False)
			roles = sorted(member.roles, reverse=True)[:-1] # Remove @everyone
			e.add_field(name='Roles', value=', '.join(role.name for role in roles), inline=False)
			e.add_field(name='Icon URL', value=icon_url, inline=False)
		await ctx.send(embed=e)
	
	@guild_only()
	@command(aliases=['server', 'guildinfo', 'serverinfo'])
	async def guild(self, ctx):
		"""Retrieve information about this guild."""
		guild = ctx.guild
		e = discord.Embed(color=blurple)
		e.set_thumbnail(url=guild.icon_url)
		e.add_field(name='Name', value=guild.name)
		e.add_field(name='ID', value=guild.id)
		e.add_field(name='Created at', value=guild.created_at.strftime(datetime_format))
		e.add_field(name='Owner', value=guild.owner)
		e.add_field(name='Members', value=guild.member_count)
		e.add_field(name='Channels', value=len(guild.channels))
		e.add_field(name='Roles', value=len(guild.role_hierarchy)-1) # Remove @everyone
		e.add_field(name='Emoji', value=len(guild.emojis))
		e.add_field(name='Region', value=guild.region.name)
		e.add_field(name='Icon URL', value=guild.icon_url or 'This guild has no icon.')
		await ctx.send(embed=e)
	
	@command()
	async def about(self, ctx):
		"""Shows information about the bot"""
		e = discord.Embed(color=discord.Color.blue())
		e.set_thumbnail(url=self.bot.user.avatar_url)
		e.add_field(name='About', value="Dozer: A collaborative bot for FIRST Discord servers, developed by the FRC Discord Server Development Team")
		await ctx.send(embed=e)

def setup(bot):
	bot.add_cog(Info(bot))
