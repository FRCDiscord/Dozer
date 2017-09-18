import discord, discord.utils
from discord.ext.commands import has_permissions, BadArgument
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from .. import db
from ._utils import *

class Feedback(Cog):
    @group(invoke_without_command=True)
    async def feedback(self, ctx, *, input):
        content = ctx.message.content
        """Send feedback to a specific guild"""
        with db.Session() as session:
            settings = session.query(GuildFeedback).filter_by(id=ctx.guild.id).one_or_none()
        if settings is not None:
            channel = discord.utils.get(ctx.guild.channels, id=settings.feedback_channel)
            if channel is not None:
                e = discord.Embed(title="Feedback Message", color=discord.Color.blue())
                e.description = input
                e.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url)
                e.add_field(name="Sent by", value=ctx.message.author.name + "#" + ctx.message.author.discriminator)
                await channel.send(embed=e)
            else: 
                await ctx.send('Configured channel does not exist! Please consult your guild\'s admin to fix this!')
        else:
            await ctx.send('Your server\'s feedback system is not yet configured! Please tell your guild\'s admin to set the channel!')
        

    @feedback.command()
    async def config(self, ctx, id):
        """Set the feedback channel for a server by passing the channel id"""
        with db.Session() as session:
            config = session.query(GuildFeedback).filter_by(id=ctx.guild.id).one_or_none()
            if config is not None:
                config.feedback_channel = id
                session.commit()
            else:
                config = GuildFeedback(id=ctx.guild.id, feedback_channel=id)
                session.add(config)

class GuildFeedback(db.DatabaseObject):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True) #guild_id
    feedback_channel = db.Column(db.Integer)

def setup(bot):
    bot.add_cog(Feedback(bot))
