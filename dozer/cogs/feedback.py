import discord, discord.utils
from discord.ext.commands import has_permissions, BadArgument
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from .. import db
from ._utils import *

class Feedback(Cog):
    @group(invoke_without_command=True)
    async def feedback(self, ctx, input):
        """Send feedback to a specific guild"""
        with db.Session() as session:
            channel = session.query(GuildFeedback).filter_by(id=ctx.guild.id).one_or_none()
        await ctx.send(channel.feedback_channel if channel is not None else 'woops')

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
