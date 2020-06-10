-- VOICE had no change in schema

-- TEAMS had no change in schema

-- ROLES
ALTER TABLE dozer.public.missing_roles DROP CONSTRAINT missing_roles_guild_id_fkey;
DROP TABLE dozer.public.missing_members;
ALTER TABLE dozer.public.giveable_roles DROP CONSTRAINT giveable_roles_guild_id_fkey;
ALTER TABLE dozer.public.giveable_roles RENAME COLUMN id TO role_id;
DROP TABLE guilds;

-- NAMEGAME had no change in schema

-- FILTER
ALTER TABLE dozer.public.word_filters RENAME COLUMN id TO filter_id;
ALTER TABLE word_filter_infraction ALTER timestamp type timestamp USING "timestamp"::timestamp without time zone;


-- GENERAL
ALTER TABLE dozer.public.welcome_channel RENAME COLUMN id TO guild_id;

-- MODERATION
ALTER TABLE dozer.public.mutes RENAME COLUMN id TO member_id;
ALTER TABLE dozer.public.mutes RENAME COLUMN guild TO guild_id;
ALTER TABLE dozer.public.deafens RENAME COLUMN id TO member_id;
ALTER TABLE dozer.public.deafens RENAME COLUMN guild TO guild_id;
ALTER TABLE dozer.public.modlogconfig RENAME COLUMN id TO guild_id;
ALTER TABLE dozer.public.member_roles RENAME COLUMN id TO guild_id;
ALTER TABLE dozer.public.memberlogconfig RENAME COLUMN id TO guild_id;
ALTER TABLE dozer.public.messagelogconfig RENAME COLUMN id TO guild_id;
ALTER TABLE dozer.public.punishment_timers RENAME COLUMN type TO type_of_punishment;
