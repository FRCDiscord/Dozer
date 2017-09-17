import discord, discord.utils
from discord.ext.commands import has_permissions, BadArgument
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from .. import db
from ._utils import *

class Feedback(Cog):
    
    @command()
    async def feedback(self, ctx, input):
        """Send feedback to a specific guild"""
        #with db.Session() as session:
            #channel = session.query(GuildFeedback.id).filter(GuildFeedback.id == ctx.guild.id).one_or_none()
        #await ctx.send('works' if channel is None else 'woops')
        await ctx.send(GuildFeedback.__table_args__)
class GuildFeedback(db.DatabaseObject):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(db.Integer)

def setup(bot):
    bot.add_cog(Feedback(bot))
