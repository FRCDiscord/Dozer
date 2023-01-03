"""Provides some useful utilities for the Discord bot, mostly to do with cleaning."""

import re
from urllib.parse import urlencode

import discord

__all__ = ['clean', 'is_clean']

mass_mention = re.compile('@(everyone|here)')
member_mention = re.compile(r'<@\!?(\d+)>')
role_mention = re.compile(r'<@&(\d+)>')
channel_mention = re.compile(r'<#(\d+)>')


def clean(ctx, text=None, *, mass=True, member=True, role=True, channel=True):
    """Cleans the message of anything specified in the parameters passed."""
    if text is None:
        text = ctx.message.content
    cleaned_text = text
    if mass:
        cleaned_text = mass_mention.sub(lambda match: '@\N{ZERO WIDTH SPACE}' + match.group(1), cleaned_text)
    if member:
        cleaned_text = member_mention.sub(lambda match: clean_member_name(ctx, int(match.group(1))), cleaned_text)
    if role:
        cleaned_text = role_mention.sub(lambda match: clean_role_name(ctx, int(match.group(1))), cleaned_text)
    if channel:
        cleaned_text = channel_mention.sub(lambda match: clean_channel_name(ctx, int(match.group(1))), cleaned_text)
    return cleaned_text


def is_clean(ctx, text=None):
    """Checks if the message is clean already and doesn't need to be cleaned."""
    if text is None:
        text = ctx.message.content
    return all(regex.search(text) is None for regex in (mass_mention, member_mention, role_mention, channel_mention))


def clean_member_name(ctx, member_id):
    """Cleans a member's name from the message."""
    member = ctx.guild.get_member(member_id)
    if member is None:
        return f'<@\N{ZERO WIDTH SPACE}{member_id:d}>'
    elif is_clean(ctx, member.display_name):
        return member.display_name
    elif is_clean(ctx, str(member)):
        return str(member)
    else:
        return f'<@\N{ZERO WIDTH SPACE}{member.id:d}>'


def clean_role_name(ctx, role_id):
    """Cleans role pings from messages."""
    role = discord.utils.get(ctx.guild.roles, id=role_id)  # Guild.get_role doesn't exist
    if role is None:
        return f'<@&\N{ZERO WIDTH SPACE}{role_id:d}>'
    elif is_clean(ctx, role.name):
        return '@' + role.name
    else:
        return f'<@&\N{ZERO WIDTH SPACE}{role.id:d}>'


def clean_channel_name(ctx, channel_id):
    """Cleans channel mentions from messages."""
    channel = ctx.guild.get_channel(channel_id)
    if channel is None:
        return f'<#\N{ZERO WIDTH SPACE}{channel_id:d}>'
    elif is_clean(ctx, channel.name):
        return '#' + channel.name
    else:
        return f'<#\N{ZERO WIDTH SPACE}{channel.id:d}>'


def pretty_concat(strings, single_suffix='', multi_suffix=''):
    """Concatenates things in a pretty way"""
    if len(strings) == 1:
        return strings[0] + single_suffix
    elif len(strings) == 2:
        return f'{strings[0]} and {strings[1]}{multi_suffix}'
    else:
        return f'{", ".join(strings[:-1])}, and {strings[-1]}{multi_suffix}'


def oauth_url(client_id, permissions=None, guild=None, redirect_uri=None):
    """A helper function that returns the OAuth2 URL for inviting the bot
    into guilds.

    Parameters
    -----------
    client_id: :class:`str`
        The client ID for your bot.
    permissions: :class:`~discord.Permissions`
        The permissions you're requesting. If not given then you won't be requesting any
        permissions.
    guild: :class:`~discord.Guild`
        The guild to pre-select in the authorization screen, if available.
    redirect_uri: :class:`str`
        An optional valid redirect URI.

    Returns
    --------
    :class:`str`
        The OAuth2 URL for inviting the bot into guilds.
    """
    url = f'https://discord.com/oauth2/authorize?client_id={client_id}&scope=bot%20applications.commands'
    if permissions is not None:
        url = url + '&permissions=' + str(permissions.value)
    if guild is not None:
        url = url + "&guild_id=" + str(guild.id)
    if redirect_uri is not None:
        url = url + "&response_type=code&" + urlencode({'redirect_uri': redirect_uri})
    return url
