from discord.ext.commands import has_permissions, bot_has_permissions
from .. import db
from ._utils import *
import discord


# Member logging: In this revision: Added member log configuration settings, on_member_join added, added on_member_remove. Todo: fix member format and test. (will have to do at home because I don't have the TestAccountPad at school)
# Todo (others): Message edit and deletion logging, mutes (including timed/self mutes)
class Moderation(Cog):
    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def ban(self, ctx, user_mentions: discord.User, *, reason):
        "Bans the user mentioned."
        usertoban = user_mentions
        howtounban = "When it's time to unban, here's the ID to unban: <@{} >".format(usertoban.id)
        modlogmessage = "{} has been banned by {} because {}. {}".format(usertoban, ctx.author.mention, reason,
                                                                         howtounban)
        await ctx.guild.ban(usertoban)
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
        await ctx.guild.unban(usertoban)
        modlogmessage = "{} has been unbanned by {} because {}".format(usertoban, ctx.author.mention, reason)
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
        await ctx.guild.kick(usertokick)
        modlogmessage = "{} has been kicked by {} because {}".format(usertokick, ctx.author.mention, reason)
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
    async def modlogconfig(self, ctx, channel_mentions: discord.TextChannel):
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

    @command()
    @has_permissions(administrator=True)
    async def memberlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        print(channel_mentions)
        with db.Session() as session:
            config = session.query(Guildmemberlog).filter_by(id=str(ctx.guild.id)).one_or_none()
            if config is not None:
                print("config is not none")
                config.name = ctx.guild.name
                config.memberlog_channel = str(channel_mentions.id)
            else:
                print("Config is none")
                config = Guildmemberlog(id=ctx.guild.id, memberlog_channel=channel_mentions.id, name=ctx.guild.name)
                session.add(config)
            await ctx.send(ctx.message.author.mention + ', memberlog settings configured!')

    async def on_member_join(self, member):
        memberjoinedmessage = "{} has joined the server! Enjoy your stay!".format(member.display_name)
        with db.Session() as session:
            memberlogchannel = session.query(Guildmemberlog).filter_by(id=member.guild.id).one_or_none()
            if memberlogchannel is not None:
                channel = member.guild.get_channel(memberlogchannel.memberlog_channel)
                await channel.send(memberjoinedmessage)

    async def on_member_remove(self, member):
        memberleftmessage = "{} has left the server!".format(member.display_name)
        with db.Session() as session:
            memberlogchannel = session.query(Guildmemberlog).filter_by(id=member.guild.id).one_or_none()
            if memberlogchannel is not None:
                channel = member.guild.get_channel(memberlogchannel.memberlog_channel)
                await channel.send(memberleftmessage)


class Guildmodlog(db.DatabaseObject):
    __tablename__ = 'modlogconfig'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    modlog_channel = db.Column(db.Integer)


class Guildmemberlog(db.DatabaseObject):
    __tablename__ = 'memberlogconfig'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    memberlog_channel = db.Column(db.Integer)


def setup(bot):
    bot.add_cog(Moderation(bot))
