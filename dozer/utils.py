import discord, re

__all__ = ['clean', 'is_clean']

mass_mention = re.compile('@(everyone|here)')
member_mention = re.compile(r'<@\!?(\d+)>')
role_mention = re.compile(r'<@&(\d+)>')
channel_mention = re.compile(r'<#(\d+)>')

def clean(ctx, text=None, *, clean_channels=True):
	if text is None:
		text = ctx.message.content
	cleaned_text = mass_mention.sub(lambda match: '@\N{ZERO WIDTH SPACE}' + match.group(1), text)
	cleaned_text = member_mention.sub(lambda match: clean_member_name(ctx, int(match.group(1))), cleaned_text)
	cleaned_text = role_mention.sub(lambda match: clean_role_name(ctx, int(match.group(1))), cleaned_text)
	cleaned_text = channel_mention.sub(lambda match: clean_channel_name(ctx, int(match.group(1))), cleaned_text)
	return cleaned_text

def is_clean(ctx, text=None):
	if text is None:
		text = ctx.message.content
	return all(regex.search(text) is None for regex in (mass_mention, member_mention, role_mention, channel_mention))

def clean_member_name(ctx, member_id):
	member = ctx.guild.get_member(member_id)
	if member is None:
		return '<@\N{ZERO WIDTH SPACE}%d>' % member_id
	elif is_clean(ctx, member.display_name):
		return member.display_name
	elif is_clean(ctx, str(member)):
		return str(member)
	else:
		return '<@\N{ZERO WIDTH SPACE}%d>' % member.id

def clean_role_name(ctx, role_id):
	role = discord.utils.get(ctx.guild.roles, id=role_id) # Guild.get_role doesn't exist
	if role is None:
		return '<@&\N{ZERO WIDTH SPACE}%d>' % role_id
	elif is_clean(ctx, role.name):
		return '@' + role.name
	else:
		return '<@&\N{ZERO WIDTH SPACE}%d>' % role.id

def clean_channel_name(ctx, channel_id):
	channel = ctx.guild.get_channel(channel_id)
	if channel is None:
		return '<#\N{ZERO WIDTH SPACE}%d>' % channel_id
	elif is_clean(ctx, channel.name):
		return '#' + channel.name
	else:
		return '<#\N{ZERO WIDTH SPACE}%d>' % channel.id

def pretty_concat(strings, single_suffix='', multi_suffix=''):
	if len(strings) == 1:
		return strings[0] + single_suffix
	elif len(strings) == 2:
		return '{} and {}{}'.format(*strings, multi_suffix)
	else:
		return '{}, and {}{}'.format(', '.join(strings[:-1]), strings[-1], multi_suffix)
