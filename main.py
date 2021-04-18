import aiohttp
import asyncio
import datetime
import discord
from discord.ext.tasks import loop
from discord.ext import commands
from enum import Enum, unique
import functools
import git
import io
import json
import logging
import os
import params
import pickle
import sqlite3
import sys
import traceback

from lobbies import Lobby, BELL_EMOJI, NOBELL_EMOJI
from replays import ReplayData, replays_load_emojis

ROOT_DIR = os.path.dirname(os.path.realpath(__file__))

def get_source_version():
    repo = git.Repo(ROOT_DIR)
    head_commit_sha = repo.head.commit.binsha
    all_commits = repo.iter_commits()
    total = 0
    index = -1
    for commit in all_commits:
        if commit.binsha == head_commit_sha:
            index = total
        total += 1

    if index == -1:
        raise Exception("HEAD commit sha not found: {}".format(repo.head.commit.hexsha))
    return total - index

@unique
class MessageType(Enum):
    CONNECT = "connect"
    CONNECT_ACK = "connectack"
    LET_MASTER = "letmaster"
    ENSURE_DISPLAY = "ensure"
    SEND_DB = "senddb"
    SEND_DB_ACK = "senddback"
    SEND_WORKSPACE = "sendws"
    SEND_WORKSPACE_ACK = "sendwsack"

class Message:
    def __init__(self, timestamp, message):
        self.timestamp = timestamp
        self.message = message

class MessageHub:
    MAX_AGE_SECONDS = 5 * 60

    def __init__(self):
        self._message_queues = {}
        for message_type in MessageType:
            self._message_queues[message_type] = []

    def on_message(self, message_type, message):
        assert isinstance(message_type, MessageType)
        assert isinstance(message, str)
        assert message_type in self._message_queues

        # TODO should I use the "real" message timestamp?
        timestamp_now = datetime.datetime.now()
        msg = Message(timestamp_now, message)
        self._message_queues[message_type].append(msg)

        # Trim old messages based on max age
        timestamp_cutoff = timestamp_now - datetime.timedelta(seconds=MessageHub.MAX_AGE_SECONDS)
        for message_type in self._message_queues.keys():
            self._message_queues[message_type] = [
                m for m in self._message_queues[message_type] if m.timestamp > timestamp_cutoff
            ]

    def got_message(self, message_type, window_seconds, return_name=None):
        assert isinstance(message_type, MessageType)
        assert message_type in self._message_queues

        timestamp_cutoff = datetime.datetime.now() - datetime.timedelta(seconds=window_seconds)
        messages_in_window = [
            m for m in self._message_queues[message_type] if m.timestamp > timestamp_cutoff
        ]
        if return_name is None:
            return len(messages_in_window) > 0
        else:
            assert message_type == MessageType.ENSURE_DISPLAY
            for message in messages_in_window:
                if message != "":
                    kv = parse_ensure_display_value(message)
                    if kv[0] == return_name:
                        return True
            return False

# constants
DB_FILE_PATH = os.path.join(ROOT_DIR, "IBCE_WARN.db")
DB_ARCHIVE_PATH = os.path.join(ROOT_DIR, "archive", "IBCE_WARN.db")
VERSION = get_source_version()
print("Source version {}".format(VERSION))

# discord connection
client_intents = discord.Intents().default()
client_intents.members = True
client_intents.reactions = True
_client = discord.ext.commands.Bot(command_prefix="!", intents=client_intents)
_client.remove_command("help")

_guild = None
_bnet_channel = None
_ent_channel = None

# communication
_initialized = False
_kv_entries = []
_com_channel = None
_im_master = False
_alive_instances = set()
_master_instance = None
_callbacks = []
_message_hub = MessageHub()
_is_master_timeout = True

# globals / workspace
_open_lobbies = []
_ent_down_tries = 0
_wc3stats_down_tries = 0

class TimedCallback:
    def __init__(self, t, func, *args, **kwargs):
        self._timeout = t
        self.callback = functools.partial(func, *args, **kwargs)
        self._task = asyncio.ensure_future(self._job())

    async def _job(self):
        await asyncio.sleep(self._timeout)
        await self.callback()

    def cancel(self):
        self._task.cancel()

async def com(to_id, message_type, message = "", file = None):
    assert isinstance(to_id, int)
    assert isinstance(message_type, MessageType)
    assert isinstance(message, str)

    payload = "/".join([
        str(params.BOT_ID),
        str(to_id),
        message_type.value,
        message
    ])
    if file is None:
        await _com_channel.send(payload)
    else:
        await _com_channel.send(payload, file=file)

def archive_db():
    archive_dir = os.path.dirname(DB_ARCHIVE_PATH)
    if not os.path.exists(archive_dir):
        os.mkdir(archive_dir)

    if os.path.exists(DB_FILE_PATH):
        os.replace(DB_FILE_PATH, DB_ARCHIVE_PATH)

async def update_db(db_bytes):
    archive_db()
    with open(DB_FILE_PATH, "wb") as f:
        f.write(db_bytes)

async def send_db(to_id):
    with open(DB_FILE_PATH, "rb") as f:
        await com(to_id, MessageType.SEND_DB, "", discord.File(f))

def update_workspace(workspace_bytes):
    global _open_lobbies
    global _okib_channel
    global _okib_message_id
    global _list_content
    global _okib_members
    global _laterib_members
    global _noib_members
    global _gatherer
    global _gathered
    global _gather_time

    workspace_obj = pickle.loads(workspace_bytes)
    logging.info("Updating workspace: {}".format(workspace_obj))

    # Lobbies
    _open_lobbies = workspace_obj["open_lobbies"]
    for key, value in workspace_obj["lobby_message_ids"].items():
        globals()[key] = value

    # OKIB
    channel_id = workspace_obj["okib_channel_id"]
    if channel_id != None:
        _okib_channel = _client.get_channel(channel_id)
        if _okib_channel == None:
            logging.error("Failed to get OKIB channel from id {}".format(channel_id))
            return False

    _okib_message_id = workspace_obj["okib_message_id"]
    _list_content = workspace_obj["list_content"]

    _okib_members = [_guild.get_member(mid) for mid in workspace_obj["okib_member_ids"]]
    if None in _okib_members:
        logging.error("Failed to get an OKIB member from ID, {} from {}".format(_okib_members, workspace_obj["okib_member_ids"]))
        return False
    _laterib_members = [_guild.get_member(mid) for mid in workspace_obj["laterib_member_ids"]]
    if None in _laterib_members:
        logging.error("Failed to get a laterIB member from ID, {} from {}".format(_laterib_members, workspace_obj["laterib_member_ids"]))
        return False
    _noib_members = [_guild.get_member(mid) for mid in workspace_obj["noib_member_ids"]]
    if None in _noib_members:
        logging.error("Failed to get a member from ID, {} from {}".format(_noib_members, workspace_obj["noib_member_ids"]))
        return False

    gatherer_id = workspace_obj["gatherer_id"]
    if gatherer_id != None:
        _gatherer = _guild.get_member(gatherer_id)
        if _gatherer == None:
            logging.error("Failed to get member from id {}".format(gatherer_id))
            return False

    _gathered = workspace_obj["gathered"]
    _gather_time = workspace_obj["gather_time"]
    return True

async def send_workspace(to_id):
    lobby_message_ids = {}
    for key, value in globals().items():
        if "lobbymsg" in key:
            lobby_message_ids[key] = value


    workspace_obj = {
        # Lobbies
        "open_lobbies": _open_lobbies,
        "lobby_message_ids": lobby_message_ids,

        # OKIB
        "okib_channel_id": None if _okib_channel == None else _okib_channel.id,
        "okib_message_id": _okib_message_id,
        "list_content": _list_content,
        "okib_member_ids": [m.id for m in _okib_members],
        "laterib_member_ids": [m.id for m in _laterib_members],
        "noib_member_ids": [m.id for m in _noib_members],
        "gatherer_id": None if _gatherer == None else _gatherer.id,
        "gathered": _gathered,
        "gather_time": _gather_time
    }
    logging.info("Sending workspace: {}".format(workspace_obj))

    workspace_bytes = io.BytesIO(pickle.dumps(workspace_obj))
    await com(to_id, MessageType.SEND_WORKSPACE, "", discord.File(workspace_bytes))

def update_source_and_reset():
    repo = git.Repo(ROOT_DIR)
    for remote in repo.remotes:
        if remote.name == "origin":
            logging.info("Pulling latest code from remote {}".format(remote))
            remote.pull()

            new_version = get_source_version()
            logging.info("New version: {}".format(new_version))
            if new_version <= VERSION:
                logging.error("Attempted to update, but version didn't upgrade ({} to {})".format(VERSION, new_version))

            if params.REBOOT_ON_UPDATE:
                logging.info("Rebooting")
                os.system("sudo shutdown -r now")
            else:
                logging.info("Exiting")
                exit()

def parse_ensure_display_value(message):
    kv = message.split("=")
    value = None
    if len(kv[1]) > 0:
        data_type = kv[1][0]
        value_str = kv[1][1:]
        if data_type == "f":
            value = float(value_str)
        elif data_type == "i":
            value = int(value_str)
        elif data_type == "s":
            value = value_str
        else:
            raise ValueError("Unhandled return type {}".format(data_type))

    return (kv[0], value)

async def parse_bot_com(from_id, message_type, message, attachment):
    global _initialized
    global _im_master
    global _alive_instances
    global _master_instance
    global _callbacks
    global _message_hub

    if message_type == MessageType.CONNECT:
        if _im_master:
            await com(from_id, MessageType.CONNECT_ACK, str(VERSION) + "+")
            # It is master's responsibility to send DB and workspace to synchronize newcomer
            await send_db(from_id)
            await send_workspace(from_id)
        else:
            await com(from_id, MessageType.CONNECT_ACK, str(VERSION))

        version = int(message)
        if version == VERSION:
            _alive_instances.add(from_id)
        elif version > VERSION:
            _alive_instances.add(from_id)
            logging.info("Bot instance {} running newer version {}, updating...".format(from_id, version))
            update_source_and_reset()
        else:
            # TODO outdated version
            pass
        logging.info("After CONNECT message, instances {}".format(_alive_instances))
    elif message_type == MessageType.CONNECT_ACK:
        message_trim = message
        if message[-1] == "+":
            logging.info("Received connect ack from master instance {}".format(from_id))
            message_trim = message[:-1]
            _alive_instances.add(params.BOT_ID)
            _master_instance = from_id
            for callback in _callbacks: # clear init's self_promote callback
                callback.cancel()
            _callbacks = []
        version = int(message_trim)
        _alive_instances.add(from_id)
        logging.info("After CONNECT_ACK message, instances {}, master {}".format(_alive_instances, _master_instance))
    elif message_type == MessageType.LET_MASTER:
        if _im_master:
            logging.warning("I was unworthy :(")
            _im_master = False
        _master_instance = from_id
    elif message_type == MessageType.ENSURE_DISPLAY:
        for callback in _callbacks:
            callback.cancel()
        _callbacks = []
        if message != "":
            kv = parse_ensure_display_value(message)
            globals()[kv[0]] = kv[1]
        if from_id != _master_instance:
            _alive_instances.remove(_master_instance)
            _master_instance = from_id
            logging.info("Master is now {}".format(from_id))
    elif message_type == MessageType.SEND_DB:
        db_bytes = await attachment.read()
        await update_db(db_bytes)
        await com(from_id, MessageType.SEND_DB_ACK)
    elif message_type == MessageType.SEND_DB_ACK:
        pass
    elif message_type == MessageType.SEND_WORKSPACE:
        workspace_bytes = await attachment.read()
        if not update_workspace(workspace_bytes):
            pass # TODO eh, whatever...
        await com(from_id, MessageType.SEND_WORKSPACE_ACK)
        # This is the last step for bot instance connection
        _initialized = True
    elif message_type == MessageType.SEND_WORKSPACE_ACK:
        pass
    else:
        raise Exception("Unhandled message type {}".format(message_type))

    _message_hub.on_message(message_type, message)

# Promotes this bot instance to master
async def self_promote():
    global _initialized
    global _im_master
    global _master_instance

    _initialized = True
    _im_master = True
    _master_instance = params.BOT_ID
    # Needed for initialization. Alternatively, can use function arg (what archi was doing)
    if params.BOT_ID not in _alive_instances:
        _alive_instances.add(params.BOT_ID)
    await com(-1, MessageType.LET_MASTER)
    logging.info("I'm in charge!")

# Wrapper around channel.send that only returns the int message ID
async def send_message(channel, *args, **kwargs):
    message = await channel.send(*args, **kwargs)
    return message.id

async def send_message_with_bell_reactions(channel, *args, **kwargs):
    message = await channel.send(*args, **kwargs)
    await message.add_reaction(BELL_EMOJI)
    await message.add_reaction(NOBELL_EMOJI)
    return message.id

async def ensure_display_backup(func, *args, window=2, return_name=None, **kwargs):
    global _master_instance
    global _alive_instances
    global _callbacks
    global _is_master_timeout

    logging.info("ensure_display_backup: _master_instance {}, _alive_instances {}".format(_master_instance, _alive_instances))

    if _is_master_timeout:
        if _master_instance == None:
            _alive_instances.remove(max(_alive_instances))
        else:
            _alive_instances.remove(_master_instance)
            _master_instance = None

        if max(_alive_instances) == params.BOT_ID:
            await self_promote()

        _is_master_timeout = False
        # All callbacks including this one now need to execute, but not resolve master's timeout
        for callback in _callbacks:
            callback.cancel()
            await callback.callback()
        _is_master_timeout = True
    else:
        await ensure_display(func, *args, window=window, return_name=return_name, **kwargs)

async def ensure_display(func, *args, window=2, return_name=None, **kwargs):
    global _callbacks

    if _im_master:
        result = await func(*args, **kwargs)
        message = ""
        if return_name is not None:
            globals()[return_name] = result
            message = return_name + "="
            # TODO should we allow return_name to be set if result is None?
            if result is not None:
                if isinstance(result, float):
                    message += "f"
                elif isinstance(result, int):
                    message += "i"
                elif isinstance(result, str):
                    message += "s"
                else:
                    raise ValueError("Unhandled return type {}".format(type(result)))
                message += str(result)

        await com(-1, MessageType.ENSURE_DISPLAY, message)
    else:
        # Only create a backup callback if no ENSURE_DISPLAY messages have been seen for the given
        # timeout window. If a return_name is given, we require previous messages to have
        # that return name as well.
        if not _message_hub.got_message(MessageType.ENSURE_DISPLAY, window, return_name):
            _callbacks.append(TimedCallback(window, ensure_display_backup, func, *args, window=window, return_name=return_name, **kwargs))

@_client.command()
async def ping(ctx):
    if isinstance(ctx.channel, discord.channel.DMChannel):
        logging.info("pingpong")
        await ensure_display(ctx.channel.send, "pong")

@_client.command()
async def update(ctx, bot_id):  # TODO default bot_id=None ??
    global _master_instance
    global _alive_instances

    bot_id = int(bot_id)
    if bot_id == params.BOT_ID:
        # No ensure_display here because this isn't a distributed action
        await ctx.channel.send("Updating code and restarting...")
        update_source_and_reset()
    else:
        if bot_id in _alive_instances:
            _alive_instances.remove(bot_id)
        else:
            logging.error("Updating instance not in alive instances: {}".format(_alive_instances))

        if _master_instance == bot_id:
            _master_instance = None
            if max(_alive_instances) == params.BOT_ID:
                await self_promote()

@_client.event
async def on_ready():
    global _guild
    global _bnet_channel
    global _ent_channel
    global _com_channel
    global _initialized
    global _alive_instances
    global _callbacks
    global _okib_emote
    global _laterib_emote
    global _noib_emote
    global _EU_role
    global _NA_role
    global _KR_role

    BNET_CHANNEL_NAME = "pub-games"
    ENT_CHANNEL_NAME = "general-chat"
    
    guild_ib = None
    guild_com = None
    for guild in _client.guilds:
        if guild.name == params.GUILD_NAME:
            guild_ib = guild
        if guild.id == params.COM_GUILD_ID:
            guild_com = guild

    if guild_ib is None:
        raise Exception("IB guild not found: \"{}\"".format(params.GUILD_NAME))
    if guild_com is None:
        raise Exception("Com virtual guild not found")

    channel_bnet = None
    channel_ent = None
    for channel in guild_ib.text_channels:
        if channel.name == BNET_CHANNEL_NAME:
            channel_bnet = channel
        if channel.name == ENT_CHANNEL_NAME:
            channel_ent = channel
    if channel_bnet is None:
        raise Exception("Pub channel not found: \"{}\" in guild \"{}\"".format(BNET_CHANNEL_NAME, guild_ib.name))
    if channel_ent is None:
        raise Exception("ENT channel not found: \"{}\" in guild \"{}\"".format(ENT_CHANNEL_NAME, guild_ib.name))

    channel_com = None
    for channel in guild_com.text_channels:
        if channel.id == params.COM_CHANNEL_ID:
            channel_com = channel
    if channel_com is None:
        raise Exception("Com channel not found")

    _guild = guild_ib
    _bnet_channel = channel_bnet
    _ent_channel = channel_ent
    _EU_role = discord.utils.get(_guild.roles, id=766268372252884994)
    _NA_role = discord.utils.get(_guild.roles, id=773269638116802661)
    _KR_role = discord.utils.get(_guild.roles, id=800299277842382858)
    _okib_emote = _client.get_emoji(OKIB_EMOJI_ID)
    _laterib_emote = _client.get_emoji(LATERIB_EMOJI_ID)
    _noib_emote = _client.get_emoji(NOIB_EMOJI_ID)
    replays_load_emojis(_guild.emojis)

    logging.info("Bot \"{}\" connected to Discord on guild \"{}\", pub channel \"{}\"".format(_client.user, guild_ib.name, channel_bnet.name))
    await _client.change_presence(activity=None)
    _com_channel = channel_com

    logging.info("Connecting to bot network...")
    await com(-1, MessageType.CONNECT, str(VERSION))
    _callbacks.append(TimedCallback(3, self_promote))

@_client.event
async def on_message(message):
    if message.author.id == _client.user.id and message.channel == _com_channel:
        # from this bot user
        message_split = message.content.split("/")
        if len(message_split) != 4:
            logging.error("Invalid bot com: {}".format(message.content))
            return

        from_id = int(message_split[0])
        to_id = int(message_split[1])
        message_type = MessageType(message_split[2])
        content = message_split[3]
        if from_id != params.BOT_ID and (to_id == -1 or to_id == params.BOT_ID):
            # from another bot instance
            logging.info("Communication received from {} to {}, {}, content = {}".format(from_id, to_id, message_type, content))

            attachment = None
            if message.attachments:
                attachment = message.attachments[0]
            await parse_bot_com(from_id, message_type, content, attachment)
    else:
        await check_replay(message)
        await _client.process_commands(message)

async def remove_reaction(channel_id, message_id, emoji, member):
    channel = _client.get_channel(channel_id)
    message = await channel.fetch_message(message_id)
    await message.remove_reaction(emoji, member)


# ==== OKIB ========================================================================================

NO_POWER_MSG = "You do not have enough power to perform such an action."
OKIB_EMOJI_ID = 506072066039087164
LATERIB_EMOJI_ID = 624308183334125568
NOIB_EMOJI_ID = 477544228629512193
IB_EMOJI_ID = 451846742661398528
IB2_EMOJI_ID = 590986772734017536
OKIB_EMOJI_STRING = "<:okib:{}>".format(OKIB_EMOJI_ID)
NOIB_EMOJI_STRING = "<:noib:{}>".format(NOIB_EMOJI_ID)
OKIB_GATHER_EMOJI_STRING = "<:ib:{}><:ib2:{}>".format(IB_EMOJI_ID, IB2_EMOJI_ID)
OKIB_GATHER_PLAYERS = 8 # not pointless - sometimes I use this for testing

_okib_emote = None
_laterib_emote = None
_noib_emote = None

_okib_channel =  None
_okib_message_id = None
_list_content = ""
_okib_members = []
_laterib_members = []
_noib_members = []
_gatherer = None
_gathered = False
_gather_time = datetime.datetime.now()

async def gather():
    gather_list_string = " ".join([member.mention for member in _okib_members])
    await _okib_channel.send(gather_list_string + " Time to play !")
    await _okib_channel.send(OKIB_EMOJI_STRING)
    for member in _okib_members:
        try:
            await member.send("Time to play !")
        except Exception as e:
            #Should be an logging.error there but since this might happen quite frequently i dont want it to show as "abnormal"
            logging.warning("Error sending DM to {}, {}".format(member.name, e))
            traceback.print_exc()
        

async def combinator3000(*args):
    for f in args:
        await f()
        
async def list_update():
    global _list_content
    
    okib_list_string = ", ".join([member.display_name for member in _okib_members])
    noib_list_string = ", ".join([member.display_name for member in _noib_members])
    _list_content = "{} asks : {}\n{} {}/{} : {}\n{} : {}".format(
        _gatherer.display_name, OKIB_GATHER_EMOJI_STRING,
        OKIB_EMOJI_STRING, len(_okib_members), OKIB_GATHER_PLAYERS, okib_list_string,
        NOIB_EMOJI_STRING, noib_list_string
    )

async def check_almost_gather():
    #print(len(_okib_members)+round(0.1+len(_laterib_members)/2))
    if len(_okib_members)+round(0.1+len(_laterib_members)/2) >= OKIB_GATHER_PLAYERS and not _gathered:
        for member in _laterib_members:
            try:
                await member.send("Hey, you are :laterib: and our radar indicates that the lobby gather is almost completed !! \nThis might be a great time for you to think about :okib: ;)")
            except Exception as e:
                #Should be an logging.error there but since this might happen quite frequently i dont want it to show as "abnormal"
                logging.warning("Error sending DM to {}, {}".format(member.name, e))
                traceback.print_exc()
            
def gather_check():
    global _gathered
    if len(_okib_members) >= OKIB_GATHER_PLAYERS and not _gathered:
        return True
    if len(_okib_members) < OKIB_GATHER_PLAYERS and _gathered:
        _gathered = False
        return False

async def up(ctx):
    global _okib_message_id
    
    if _okib_message_id is not None:
        message = await _okib_channel.fetch_message(_okib_message_id)
        await message.delete()

    okib_message = await ctx.send(_list_content)
    await okib_message.add_reaction(_okib_emote)
    await okib_message.add_reaction(_laterib_emote)
    await okib_message.add_reaction(_noib_emote)
    await ctx.message.delete()
    _okib_message_id = okib_message.id
    return _okib_message_id
    
@_client.command()
async def okib(ctx, arg=None):
    global _okib_channel
    global _okib_message_id
    global _okib_members
    global _laterib_members
    global _noib_members
    global _gatherer
    global _gathered
    global _gather_time

    adv = False
    #PUB OKIB
    if ctx.channel ==  _bnet_channel:
        if ctx.message.author.roles[-1] < _guild.get_role(params.PUB_HOST_ID):
            await ensure_display(ctx.channel.send, NO_POWER_MSG)
            return
    #/PUB OKIB
    elif ctx.message.author.roles[-1] <= _guild.get_role(params.PEON_ID):
        await ensure_display(ctx.channel.send, NO_POWER_MSG)
        return
    if ctx.message.author.roles[-1] >= _guild.get_role(params.SHAMAN_ID) or ctx.message.author == _gatherer:
        adv = True
    if adv == False and arg != None:
        await ensure_display(ctx.channel.send, NO_POWER_MSG)
        return
    
    if  _okib_channel is not None and _okib_channel != ctx.channel:
        await ensure_display(ctx.channel.send, "gathering is already in progress in channel " + _okib_channel.mention)
        return
    
    modify = False
    for user in ctx.message.mentions:
        if user not in _okib_members:
            _okib_members.append(user)
            modify = True
        if user in _noib_members:
            _noib_members.remove(user)
            modify = True
        if user in _laterib_members:
            _laterib_members.remove(user)
    
    if _okib_channel is None:
        _gatherer = ctx.message.author
        _gather_time = datetime.datetime.now()
        # Check for option
        if adv and arg == 'retrieve':
            pass
        else:
            _gathered = False
            _okib_members = []
            _noib_members = []
            for user in ctx.message.mentions:
                if user not in _okib_members:
                    _okib_members.append(user)
                if user in _noib_members:
                    _noib_members.remove(user)
                if user in _laterib_members:
                    _laterib_members.remove(user)

        _okib_channel = ctx.channel
        await list_update()
        await ensure_display(up, ctx, return_name="_okib_message_id")
        modify = False

    elif arg == None:
        await ensure_display(up, ctx, return_name="_okib_message_id")
            
    if arg == 'retrieve':
        await list_update()
        gather_check()
        if _gathered:
            await ensure_display(up, ctx, return_name="_okib_message_id")
    elif modify:
        await list_update()
        if gather_check():
            await ensure_display(functools.partial(
                combinator3000,
                ctx.message.delete,
                functools.partial(
                    (await _okib_channel.fetch_message(_okib_message_id)).edit,
                    content=_list_content),
                gather
            ))
            _gathered = True
        else:
            await ensure_display(functools.partial(
                combinator3000,
                ctx.message.delete,
                check_almost_gather,
                functools.partial(
                    (await _okib_channel.fetch_message(_okib_message_id)).edit,
                    content=_list_content
                )
            ))

@_client.command()
async def noib(ctx):
    global _okib_members
    global _laterib_members
    global _noib_members
    global _okib_channel
    global _okib_message_id
    
    #PUB OKIB
    if ctx.channel ==  _bnet_channel and ctx.message.author.roles[-1] >= _guild.get_role(params.PUB_HOST_ID):
        pass
    #/PUB OKIB
    elif ctx.message.author.roles[-1] <= _guild.get_role(params.PEON_ID):
        await ensure_display(ctx.channel.send, NO_POWER_MSG)
        return
    if ctx.message.author.roles[-1] < _guild.get_role(params.SHAMAN_ID) and ctx.message.author != _gatherer:
        if datetime.datetime.now() < (_gather_time + datetime.timedelta(hours=2)):
            await ensure_display(ctx.channel.send, NO_POWER_MSG)
            return
        pass

    if not ctx.message.mentions:
        if _okib_message_id is not None:
            await ensure_display(functools.partial(
                combinator3000,
                ctx.message.delete,
                (await _okib_channel.fetch_message(_okib_message_id)).delete
            ))
        _okib_message_id = None
        _okib_channel = None
        
    modify = False
    for user in ctx.message.mentions:
        if user not in _noib_members:
            _noib_members.append(user)
            modify = True
        if user in _okib_members:
            _okib_members.remove(user)
            modify = True
        if user in _laterib_members:
            _laterib_members.remove(user)
            
    if modify:
        await list_update()
        gather_check()
        await ensure_display(functools.partial(
            combinator3000,
            ctx.message.delete,
            functools.partial(
                (await _okib_channel.fetch_message(_okib_message_id)).edit,
                content=_list_content)
        ))
        
async def okib_on_reaction_add(channel_id, message_id, emoji, member):
    global _okib_members
    global _laterib_members
    global _noib_members
    global _gathered
    
    if message_id == _okib_message_id and member.bot == False:
        modify = False 
        if member.roles[-1] >= _guild.get_role(params.PEON_ID) or _okib_channel == _bnet_channel:
            try:
                if emoji == _okib_emote:
                    if member not in _okib_members:
                        _okib_members.append(member)
                        modify = True
                    if member in _noib_members:
                        _noib_members.remove(member)
                        modify = True
                    if member in _laterib_members:
                        _laterib_members.remove(member)

                elif emoji == _noib_emote:
                    if member not in _noib_members:
                        _noib_members.append(member)
                        modify = True
                    if member in _okib_members:
                        _okib_members.remove(member)
                        modify = True
                    if member in _laterib_members:
                        _laterib_members.remove(member)
                
                elif emoji == _laterib_emote:
                    if member not in _laterib_members:
                        _laterib_members.append(member)
                    if member in _noib_members:
                        _noib_members.remove(member)
                        modify = True
                    if member in _okib_members:
                        _okib_members.remove(member)
                        modify = True
                
            except AttributeError as e:
                traceback.print_exc()
                pass
            
            if modify:
                await list_update()
                #remove&edit
                if gather_check():
                    await ensure_display(functools.partial(
                        combinator3000,
                        gather,
                        functools.partial(
                            (await _okib_channel.fetch_message(_okib_message_id)).edit,
                            content=_list_content
                        ),
                        functools.partial(remove_reaction, channel_id, message_id, emoji, member)
                    ))
                    _gathered = True
                else:
                    await ensure_display(functools.partial(
                        combinator3000,
                        functools.partial(
                            (await _okib_channel.fetch_message(_okib_message_id)).edit,
                            content=_list_content
                        ),
                        functools.partial(remove_reaction, channel_id, message_id, emoji, member),
                        check_almost_gather
                    ))
                return
        #justremove
        await ensure_display(remove_reaction, channel_id, message_id, emoji, member)


async def pub_host_promote(member):
    channel = await member.create_dm()
    await ensure_display(channel.send, "Congratulation on being promoted to pub host !\nYou are now able to start a gather for IB games on the pub-games channel. To do so, use !okib command to start it, and !noib command to end/cancel it. Others have to answer with the :okib: and the :noib: reactions. Now you can get an idea of who in the discord is up to play a game without having to guess which players will come back, and discord members can express their interest in playing without needing to leave a message which may not be seen. By starting a gather, you're confirming you can host the game when it reach 8 players, within 20 mins. You'll get notified when it reaches 8 players.")

async def peon_promote(member):
    channel = await member.create_dm()
    await ensure_display(channel.send, "Congratulation on being promoted to peon !\nYou are now able to register for official ENT games. To do so, you have to use the :okib: and the :noib: reactions when the clan is looking for ENT players. By declaring you up for a game, you're confirming you can join the game when it starts, within 20 mins. You'll get notified when we reach desired number of players and when the game is actually hosted.")

async def grunt_promote(member):
    channel = await member.create_dm()
    await ensure_display(channel.send, "Congratulation on being promoted to grunt !\nYou are now able to start your own gather with the !okib command in the #general channel. When you do so, you have access to the !noib command to cancel your gather, don't forget to cancel it before you leave, so you don't leave an old gather for the next bot user.\nYou can now cancel anyone's gather after at least 2 hours of the first !okib command.\nYou can also remove player from your gather with the !noib @player command. Use these rights wisely.")

async def shaman_promote(member):
    channel = await member.create_dm()
    await ensure_display(channel.send, "Congratulation on being promoted to shaman !\nYou have now full access to all commands of anyone's gather. This include manually adding players (by-passing peon rank requirement) with the !okib @player command and removing any player with the !noib @player command. You can cancel anyone's gather at any time with the basic !noib. Additionally, if you find that someone accidentally cancels a gather, retrieve old list of players with the !okib retrieve command, only if a new gather hasn't been started already.")

@_client.event
async def on_member_update(before, after):
    if before.guild == _guild:
        #promoted
        if before.roles[-1] < _guild.get_role(params.PUB_HOST_ID) and after.roles[-1] == _guild.get_role(params.PUB_HOST_ID):
            await pub_host_promote(after)
            
        if before.roles[-1] < _guild.get_role(params.SHAMAN_ID) and before.roles[-1] > _guild.get_role(params.PEON_ID):
            #was grunt
            if after.roles[-1] >= _guild.get_role(params.SHAMAN_ID):
                #promoted to shaman
                await shaman_promote(after)
        elif before.roles[-1] == _guild.get_role(params.PEON_ID):
            #was peon
            if after.roles[-1] > _guild.get_role(params.PEON_ID) and after.roles[-1] < _guild.get_role(params.SHAMAN_ID):
                #promoted to grunt
                await grunt_promote(after)
            elif after.roles[-1] >= _guild.get_role(params.SHAMAN_ID):
                #promoted to shaman
                await grunt_promote(after)
                await shaman_promote(after)
        elif before.roles[-1] < _guild.get_role(params.PEON_ID):
            #was nothing
            if after.roles[-1] == _guild.get_role(params.PEON_ID):
                #promoted to peon3
                await peon_promote(after)
            elif after.roles[-1] > _guild.get_role(params.PEON_ID) and after.roles[-1] < _guild.get_role(params.SHAMAN_ID):
                #promoted to grunt
                await peon_promote(after)
                await grunt_promote(after)
            elif after.roles[-1] >= _guild.get_role(params.SHAMAN_ID):
                #promoted to shaman
                await peon_promote(after)
                await grunt_promote(after)
                await shaman_promote(after)

def nonquery(query):
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    cursor.execute(query)
    conn.commit()
    conn.close()

@_client.command()
async def warn(ctx, arg1, *, arg2=""):
    if ctx.message.author.roles[-1] < _guild.get_role(params.SHAMAN_ID):
        await ensure_display(ctx.channel.send, NO_POWER_MSG)
        return

    for user in ctx.message.mentions:
        sqlquery = "INSERT INTO Events (Event_type,Player_id,Reason,Datetime,Warner) VALUES (666,{},\"{}\",\"{}\",\"{}\")".format(user.id, arg2, datetime.datetime.now(), ctx.message.author.display_name)
        nonquery(sqlquery)
        await ensure_display(ctx.channel.send, "User <@!{}> has been warned !".format(user.id))
        
@_client.command()
async def pedigree(ctx):
    if ctx.message.author.roles[-1] < _guild.get_role(params.PEON_ID):
        await ensure_display(ctx.channel.send, NO_POWER_MSG)
        return

    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    for user in ctx.message.mentions:
        sqlquery = "SELECT player_id,Reason,Datetime,Warner FROM Events WHERE Event_type = 666 AND Player_id = " + str(user.id)
        cursor.execute(sqlquery)
        row = cursor.fetchone()
        if row is None:
            await ensure_display(ctx.channel.send, "User <@!{}> has never been warned yet !".format(user.id))
        else:
            while row:
                await ensure_display(ctx.channel.send, "{} => User <@!{}> has been warned by {} for the following reason:\n{}".format(row[2], row[0], row[3], row[1]))
                row = cursor.fetchone()
    conn.close()

# ==== MISC ========================================================================================

async def check_replay(message):
    ENSURE_DISPLAY_WINDOW = 30

    if len(message.attachments) == 0:
        return

    att = message.attachments[0]
    if ".w3g" not in att.filename:
        return

    replay = await att.read()
    timeout = aiohttp.ClientTimeout(total=ENSURE_DISPLAY_WINDOW)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        logging.info("Uploading replay {}".format(att.filename))
        response = await session.post("https://api.wc3stats.com/upload", data={
            "file": replay
        })
        if response.status != 200:
            logging.error("Replay upload failed")
            logging.error(await response.text())
            await ensure_display(message.channel.send, "Failed to upload replay `{}` with status `{}`".format(att.filename, response.status), window=ENSURE_DISPLAY_WINDOW)
            return

        response_json = await response.json()
        replay_id = response_json["body"]["id"]
        fallback_message = "Uploaded replay `{}` => https://wc3stats.com/games/{}".format(att.filename, replay_id)
        try:
            replay_data = ReplayData(response_json)
        except Exception as e:
            logging.error("Failed to parse replay data, id {}".format(replay_id))
            traceback.print_exc()
            await ensure_display(message.channel.send, fallback_message, window=ENSURE_DISPLAY_WINDOW)
            return

        content = "Uploaded replay `{}`:".format(att.filename)
        embed = replay_data.to_discord_embed()
        await ensure_display(message.channel.send, content=content, embed=embed, window=ENSURE_DISPLAY_WINDOW)

@_client.command()
async def unsub(ctx, arg1=None):
    await ensure_display(functools.partial(unsub2, ctx, arg1))
    
async def unsub2(ctx,arg1):
    if (arg1 == "EU" or arg1 == "eu"):
        await ctx.message.author.remove_roles(_EU_role)
        await ctx.message.channel.send("EU has been succesfully removed from your roles")
    if (arg1 == "NA" or arg1 == "na"):
        await ctx.message.author.remove_roles(_NA_role)
        await ctx.message.channel.send("NA has been succesfully removed from your roles")
    if (arg1 == "KR" or arg1 == "kr"):
        await ctx.message.author.remove_roles(_KR_role)
        await ctx.message.channel.send("KR has been succesfully removed from your roles")

@_client.command()
async def sub(ctx, arg1=None):
    await ensure_display(functools.partial(sub2, ctx, arg1))
    
async def sub2(ctx, arg1):
    if (arg1 == "EU" or arg1 == "eu"):
        await ctx.message.author.add_roles(_EU_role)
        await ctx.message.channel.send("EU has been succesfully added in your roles")
    if (arg1 == "NA" or arg1 == "na"):
        await ctx.message.author.add_roles(_NA_role)
        await ctx.message.channel.send("NA has been succesfully added in your roles")
    if (arg1 == "KR" or arg1 == "kr"):
        await ctx.message.author.add_roles(_KR_role)
        await ctx.message.channel.send("KR has been succesfully added in your roles")


# @_client.command()
# async def register(ctx,arg1):
#     if ctx.message.author.roles[-1] < _guild.get_role(params.GRUNT_ID):
#         await ensure_display(ctx.channel.send, NO_POWER_MSG)
#         return
#     
#     conn = sqlite3.connect(DB_FILE_PATH)
#     cursor = conn.cursor()
# 
#     #check if name is already registered
#     sqlquery = "SELECT * FROM Players WHERE ent_name = " + name
#     cursor.execute(sqlquery)
#     row = cursor.fetchone()
#     if row is not None:
#         conn.close()
#         await ensure_display(ctx.channel.send, "That ENT name has already been registered, no modification were made")
#         return
#     
#     #check if that player has already registered an ENT name, if so => modify the entry
#     sqlquery = "SELECT RowID FROM Players WHERE Player_id = " + ctx.message.author.id
#     cursor.execute(sqlquery)
#     row = cursor.fetchone()
#     if row is not None:
#         #delete the value first
#         RowID = row[0]
#         sqlquery = "DELETE FROM Players WHERE RowID = " + str(RowID)
#         cursor.execute(sqlquery)
#         conn.commit()
#     sqlquery = "INSERT INTO Players (Player_id,ent_name) VALUES (" + str(ctx.message.author.id) + "," + name + ")"
#     cursor.execute(sqlquery)
#     conn.commit()
#     conn.close()


# ==== LOBBIES =====================================================================================

LOBBY_REFRESH_RATE = 5
QUERY_RETRIES_BEFORE_WARNING = 10
ENSURE_DISPLAY_WINDOW = LOBBY_REFRESH_RATE * 2

_update_lobbies_lock = asyncio.Lock()

def lobby_get_message_id(lobby):
    key = lobby.get_message_id_key()
    if key not in globals():
        return None
    return globals()[key]

async def lobby_create_message(lobby):
    channel = _ent_channel if lobby.is_ent else _bnet_channel

    try:
        message_info = lobby.to_discord_message_info()
        if message_info is None:
            logging.info("Lobby skipped: {}".format(lobby))
            return

        logging.info("Creating lobby: {}".format(lobby))
        key = lobby.get_message_id_key()
        await ensure_display(send_message_with_bell_reactions,
            channel, content=message_info["message"], embed=message_info["embed"],
            window=ENSURE_DISPLAY_WINDOW, return_name=key
        )
    except Exception as e:
        logging.error("Failed to send message for lobby \"{}\", {}".format(lobby, e))
        traceback.print_exc()

async def lobby_update_message(lobby, is_open=True):
    channel = _ent_channel if lobby.is_ent else _bnet_channel

    message_id = lobby_get_message_id(lobby)
    if message_id is not None:
        message = None
        try:
            message = await channel.fetch_message(message_id)
        except Exception as e:
            logging.error("Error fetching message with ID {}, {}".format(message_id, e))
            traceback.print_exc()

        if message is not None:
            try:
                message_info = lobby.to_discord_message_info(is_open)
                if message_info is None:
                    logging.info("Lobby skipped: {}".format(lobby))
                    return
            except Exception as e:
                logging.error("Failed to get lobby as message info for \"{}\", {}".format(
                    lobby.name, e
                ))
                traceback.print_exc()
                return

            logging.info("Updating lobby (open={}): {}".format(is_open, lobby))
            await ensure_display(message.edit, content=message_info["message"], embed=message_info["embed"], window=ENSURE_DISPLAY_WINDOW)
    else:
        logging.error("Missing message ID on update for lobby {}".format(lobby))

    if not is_open:
        if len(lobby.subscribers) > 0:
            logging.info("Lobby closed, notifying {} subscribers".format(len(lobby.subscribers)))
            subscribers_string = "Lobby started/unhosted: **{}**\n".format(lobby.name)
            subscribers_string += ", ".join([sub.mention for sub in lobby.subscribers])
            await ensure_display(channel.send, subscribers_string)

        key = lobby.get_message_id_key()
        if key in globals():
            del globals()[key]

async def lobby_delete_message(lobby):
    channel = _ent_channel if lobby.is_ent else _bnet_channel

    message_id = lobby_get_message_id(lobby)
    if message_id is not None:
        message = None
        try:
            message = await channel.fetch_message(message_id)
        except Exception as e:
            logging.error("Error fetching message with ID {}, {}".format(message_id, e))
            traceback.print_exc()

        if message is not None:
            await ensure_display(message.delete, window=ENSURE_DISPLAY_WINDOW)
    else:
        logging.error("Missing message ID on delete for lobby {}".format(lobby))

    key = lobby.get_message_id_key()
    if key in globals():
        del globals()[key]

def get_lobby_changes(prev_lobbies, api_lobbies):
    lobbies = []
    is_prev_lobby_closed = [(lobby not in api_lobbies) for lobby in prev_lobbies]
    is_lobby_new = []
    is_lobby_updated = []
    for lobby in api_lobbies:
        is_new = lobby not in prev_lobbies
        is_updated = not is_new
        if not is_new:
            for lobby2 in prev_lobbies:
                if lobby2 == lobby:
                    lobby.subscribers = lobby2.subscribers
                    is_updated = lobby2.is_updated(lobby)
                    break

        lobbies.append(lobby)
        is_lobby_new.append(is_new)
        is_lobby_updated.append(is_updated)

    return (lobbies, is_prev_lobby_closed, is_lobby_new, is_lobby_updated)

async def report_lobbies(prev_lobbies, api_lobbies):
    changes = get_lobby_changes(prev_lobbies, api_lobbies)
    lobbies = changes[0]

    # Update messages for closed lobbies
    for i in range(len(prev_lobbies)):
        if changes[1][i]:
            await lobby_update_message(prev_lobbies[i], is_open=False)

    # Create/update messages for open lobbies
    for i in range(len(lobbies)):
        assert not (changes[2][i] and changes[3][i])
        if changes[2][i]:
            await lobby_create_message(lobbies[i])
        if changes[3][i]:
            await lobby_update_message(lobbies[i])

    return lobbies

async def update_bnet_lobbies(session, prev_lobbies):
    response = await session.get("https://api.wc3stats.com/gamelist")
    response_json = await response.json()
    if "body" not in response_json:
        raise Exception("wc3stats API response has no 'body'")
    body = response_json["body"]
    if not isinstance(body, list):
        raise Exception("wc3stats API response 'body' type is {}, not list".format(type(body)))

    lobbies = [Lobby(obj, is_ent=False) for obj in body]
    ib_lobbies = [lobby for lobby in lobbies if lobby.is_ib()]
    logging.debug("wc3stats: {}/{} IB lobbies".format(len(ib_lobbies), len(lobbies)))
    return await report_lobbies(prev_lobbies, ib_lobbies)

async def update_ent_lobbies(session, prev_lobbies):
    response = await session.get("https://host.entgaming.net/allgames")
    response_json = await response.json()
    if not isinstance(response_json, list):
        raise Exception("ENT API response type is {}, not list".format(type(response_json)))

    lobbies = [Lobby(obj, is_ent=True) for obj in response_json]
    ib_lobbies = [lobby for lobby in lobbies if lobby.is_ib()]
    logging.debug("ENT: {}/{} IB lobbies".format(len(ib_lobbies), len(lobbies)))
    return await report_lobbies(prev_lobbies, ib_lobbies)

async def update_ib_lobbies():
    global _open_lobbies
    global _ent_down_tries
    global _wc3stats_down_tries

    prev_bnet_lobbies = [lobby for lobby in _open_lobbies if not lobby.is_ent]
    prev_ent_lobbies = [lobby for lobby in _open_lobbies if lobby.is_ent]

    # Query API
    timeout = aiohttp.ClientTimeout(total=LOBBY_REFRESH_RATE/2)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        result = await asyncio.gather(
            update_bnet_lobbies(session, prev_bnet_lobbies),
            update_ent_lobbies(session, prev_ent_lobbies),
            return_exceptions=True
        )

    new_bnet_lobbies = prev_bnet_lobbies
    if isinstance(result[0], list):
        new_bnet_lobbies = result[0]
        if _wc3stats_down_tries > 0:
            _wc3stats_down_tries = 0
            await _client.change_presence(activity=None)
    else:
        logging.error("Failed to update bnet lobbies")
        _wc3stats_down_tries += 1
        if _wc3stats_down_tries > QUERY_RETRIES_BEFORE_WARNING:
            await _client.change_presence(activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="bad wc3stats lobby API"
            ))

    new_ent_lobbies = prev_ent_lobbies
    if isinstance(result[1], list):
        new_ent_lobbies = result[1]
        if _ent_down_tries > 0:
            _ent_down_tries = 0
            await _client.change_presence(activity=None)
    else:
        logging.error("Failed to update ENT lobbies")
        _ent_down_tries += 1
        if _ent_down_tries > QUERY_RETRIES_BEFORE_WARNING:
            await _client.change_presence(activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="bad ENT lobby API"
            ))

    _open_lobbies = new_bnet_lobbies + new_ent_lobbies

@_client.command()
async def getgames(ctx):
    global _open_lobbies

    if ctx.channel == _ent_channel:
        is_ent_channel = True
    elif ctx.channel == _bnet_channel:
        is_ent_channel = False
    else:
        return
    await ensure_display(ctx.message.delete)

    async with _update_lobbies_lock:
        # Clear all posted messages for open lobbies and trigger a refresh
        for lobby in _open_lobbies:
            if lobby.is_ent == is_ent_channel:
                await lobby_delete_message(lobby)

        _open_lobbies = [lobby for lobby in _open_lobbies if lobby.is_ent != is_ent_channel]
        await update_ib_lobbies()

@loop(seconds=LOBBY_REFRESH_RATE)
async def refresh_ib_lobbies():
    if not _initialized:
        return

    logging.debug("Refreshing lobby list")
    async with _update_lobbies_lock:
        await update_ib_lobbies()

async def lobbies_on_reaction_add(channel_id, message_id, emoji, member):
    if member.bot or not emoji.is_unicode_emoji() or (emoji.name != BELL_EMOJI and emoji.name != NOBELL_EMOJI):
        return

    match_lobby = False
    async with _update_lobbies_lock:
        for lobby in _open_lobbies:
            lobby_message_id = lobby_get_message_id(lobby)
            if lobby_message_id == message_id:
                match_lobby = True
                updated = False
                if emoji.name == BELL_EMOJI and member not in lobby.subscribers:
                    logging.info("User {} subbed to lobby {}".format(member.display_name, lobby))
                    lobby.subscribers.append(member)
                    updated = True
                if emoji.name == NOBELL_EMOJI and member in lobby.subscribers:
                    logging.info("User {} unsubbed from lobby {}".format(member.display_name, lobby))
                    lobby.subscribers.remove(member)
                    updated = True

                if updated:
                    await lobby_update_message(lobby)

    if match_lobby:
        await ensure_display(remove_reaction, channel_id, message_id, emoji, member)

# ==== MAIN ========================================================================================

@_client.event
async def on_raw_reaction_add(payload):
    await asyncio.gather(
        okib_on_reaction_add(
            payload.channel_id, payload.message_id, payload.emoji, payload.member
        ),
        lobbies_on_reaction_add(
            payload.channel_id, payload.message_id, payload.emoji, payload.member
        ),
        return_exceptions=True
    )

if __name__ == "__main__":
    logs_dir = os.path.join(ROOT_DIR, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    datetime_now = datetime.datetime.now()
    log_file_path = os.path.join(logs_dir, "v{}.{}.log".format(VERSION, datetime_now.strftime("%Y%m%d_%H%M%S")))
    print("Log file: {}".format(log_file_path))

    logging.basicConfig(
        filename=log_file_path, level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    refresh_ib_lobbies.start()
    _client.run(params.BOT_TOKEN)
