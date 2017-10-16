import discord, discord.utils
from discord.ext.commands import has_permissions
from .. import db
from ._utils import *
from fuzzywuzzy import fuzz

class Feedback(Cog):
    @group(invoke_without_command=True)
    async def feedback(self, ctx, *, input):
        """Send feedback to a specific guild. Only can be used from dm conversation. Format: <server> % <feedback>"""
        if type(ctx.channel) is discord.DMChannel:
            server_name = input[0:input.index(' % ')]
            content = input[input.index(' % ')+2:]
            with db.Session() as session:
                settings_list = session.query(GuildFeedback).all()
            if settings_list is not None:
                for settings in settings_list:
                    if(fuzz.partial_ratio(server_name, settings.name) > 60):
                        server = discord.utils.get(ctx.bot.guilds, id=settings.id)
                        if server is not None: channel = discord.utils.get(server.channels, id=settings.feedback_channel)
                        if channel is not None:
                            e = discord.Embed(title='Feedback Message', color=discord.Color.blue())
                            e.description = content
                            e.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url)
                            e.add_field(name='Sent by', value=ctx.message.author.name + '#' + ctx.message.author.discriminator)
                            await channel.send(embed=e)
                            await ctx.send('Feedback sent! Thank you for using Dozer!')
                        else: 
                            await ctx.send('Configured channel does not exist! Please consult your guild\'s admin to fix this!')
                    else:
                        await ctx.send('Server not found! Please adjust your spelling or check with your guild\'s admin that they have enabled this setting!')
        else:
            await ctx.send('This command cannot be used in a guild! Only in a dm conversation!')

    @feedback.command()
    @has_permissions(administrator=True)
    async def config(self, ctx, id):
        """Set the feedback channel for a server by passing the channel id"""
        with db.Session() as session:
            config = session.query(GuildFeedback).filter_by(id=ctx.guild.id).one_or_none()
            if config is not None:
                config.name = ctx.guild.name
                config.feedback_channel = id
                session.commit()
            else:
                config = GuildFeedback(id=ctx.guild.id, feedback_channel=id, name=ctx.guild.name)
                session.add(config)
            await ctx.send(ctx.message.author.mention + ', feedback settings configured!')

class GuildFeedback(db.DatabaseObject):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True) #guild_id
    name = db.Column(db.String)
    feedback_channel = db.Column(db.Integer)

def setup(bot):
    bot.add_cog(Feedback(bot))
