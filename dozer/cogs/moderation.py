from discord.ext.commands import has_permissions, bot_has_permissions
from .. import db
from ._utils import *
import discord


class Moderation(Cog):
    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def ban(self, ctx, user_mentions: discord.User, *, reason):
        "Bans the user mentioned."
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        bannedid = str(usertoban.id)
        modlogmessage = str("{} has been banned by {} because {}").format(usertobanstr, ctx.author.mention, reason)
        print("Ban detected for user", usertobanstr)
        await ctx.guild.ban(usertoban)
        howtounban = str("When it's time to unban, here's the ID to unban: <@{} >").format(bannedid)
        await ctx.send(modlogmessage)
        with db.Session() as session:
            modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
            if modlogchannel is not None:
                channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
                await channel.send(modlogmessage)
            else:
                await ctx.send("Please configure modlog channel to enable modlog functionality")

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_mentions: discord.User, *, reason):
        "Unbans the user ID mentioned."
        usertoban = user_mentions
        usertobanstr = str(usertoban)
        await ctx.guild.unban(usertoban)
        modlogmessage = str("{} has been unbanned by {} because {}").format(usertobanstr, ctx.author.mention, reason)
        await ctx.send(modlogmessage)
        with db.Session() as session:
            modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
            if modlogchannel is not None:
                channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
                await channel.send(modlogmessage)
            else:
                await ctx.send("Please configure modlog channel to enable modlog functionality")

    @command()
    @has_permissions(kick_members=True)
    @bot_has_permissions(kick_members=True)
    async def kick(self, ctx, user_mentions: discord.User, *, reason):
        "Kicks the user mentioned."
        usertokick = user_mentions
        usertokickstr = str(usertokick)
        await ctx.guild.kick(usertokick)
        modlogmessage = str("{} has been kicked by {} because {}").format(usertokickstr, ctx.author.mention, reason)
        await ctx.send(modlogmessage)
        with db.Session() as session:
            modlogchannel = session.query(Guildmodlog).filter_by(id=ctx.guild.id).one_or_none()
            if modlogchannel is not None:
                channel = ctx.guild.get_channel(modlogchannel.modlog_channel)
                await channel.send(modlogmessage)
            else:
                await ctx.send("Please configure modlog channel to enable modlog functionality")

    @command()
    @has_permissions(administrator=True)
    async def config(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        print(channel_mentions)
        with db.Session() as session:
            config = session.query(Guildmodlog).filter_by(id=str(ctx.guild.id)).one_or_none()
            if config is not None:
                print("config is not none")
                config.name = ctx.guild.name
                config.modlog_channel = str(channel_mentions.id)
            else:
                print("Config is none")
                config = Guildmodlog(id=ctx.guild.id, modlog_channel=channel_mentions.id, name=ctx.guild.name)
                session.add(config)
            await ctx.send(ctx.message.author.mention + ', modlog settings configured!')


class Guildmodlog(db.DatabaseObject):
    __tablename__ = 'modlogconfig'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    modlog_channel = db.Column(db.Integer)


def setup(bot):
    bot.add_cog(Moderation(bot))
