"""Holder for the custom join/leave messages database class and the associated methods"""
import discord
from loguru import logger

from dozer import db


async def send_log(member):
    """Sends the message for when a user joins or leave a guild"""
    config = await CustomJoinLeaveMessages.get_by(guild_id=member.guild.id)
    if len(config):
        channel = member.guild.get_channel(config[0].channel_id)
        if channel:
            embed = discord.Embed(color=0x00FF00)
            embed.set_author(name='Member Joined', icon_url=member.display_avatar.replace(format='png', size=32))
            embed.description = format_join_leave(config[0].join_message, member)
            embed.set_footer(text=f"{member.guild.name} | {member.guild.member_count} members")
            try:
                await channel.send(content=member.mention if config[0].ping else None, embed=embed)
            except discord.Forbidden:
                logger.warning(
                    f"Guild {member.guild}({member.guild.id}) has invalid permissions for join/leave logs")


def format_join_leave(template: str, member: discord.Member):
    """Formats join leave message templates
    {guild} = guild name
    {user} = user's name plus discriminator ex. SnowPlow#5196
    {user_name} = user's name without discriminator
    {user_mention} = user's mention
    {user_id} = user's ID
    """
    template = template or "{user_mention}\n{user} ({user_id})"
    return template.format(guild=member.guild, user=str(member), user_name=member.name,
                            user_mention=member.mention, user_id=member.id)


class CustomJoinLeaveMessages(db.DatabaseTable):
    """Holds custom join leave messages"""
    __tablename__ = 'memberlogconfig'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,	            
            memberlog_channel bigint NOT NULL,	   
            name varchar NOT NULL,
            send_on_verify boolean
            )""")

    def __init__(self, guild_id, channel_id=None, ping=None, join_message=None, leave_message=None, send_on_verify=False):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.ping = ping
        self.join_message = join_message
        self.leave_message = leave_message
        self.send_on_verify = send_on_verify

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = CustomJoinLeaveMessages(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                          ping=result.get("ping"),
                                          join_message=result.get("join_message"),
                                          leave_message=result.get("leave_message"),
                                          send_on_verify=result.get("send_on_verify"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            alter table memberlogconfig rename column memberlog_channel to channel_id;
            alter table memberlogconfig alter column channel_id drop not null;
            alter table {self.__tablename__} drop column IF EXISTS name;
            alter table {self.__tablename__}
                add IF NOT EXISTS ping boolean default False;
            alter table {self.__tablename__}
                add IF NOT EXISTS join_message text default null;
            alter table {self.__tablename__}
                add IF NOT EXISTS leave_message text default null;
            """)

    async def version_2(self):
        async with db.Pool.acquire() as conn:
            await conn.execute(f"alter table {self.__tablename__} "
                               f"add if not exists send_on_verify boolean default null;")

    __versions__ = [version_1, version_2]
