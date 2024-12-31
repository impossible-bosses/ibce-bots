import discord
from enum import Enum, unique
import logging
from typing import Any

from lobbies import get_map_version

_class_emoji: dict[Class, discord.Emoji] | None = None

@unique
class Difficulty(Enum):
    VE = "Very Easy"
    E = "Easy"
    M = "Moderate"
    N = "Normal"
    H = "Hard"

@unique
class Class(Enum):
    DK = "Death Knight"
    DRUID = "Druid"
    FM = "Fire Mage"
    IM = "Ice Mage"
    PALADIN = "Paladin"
    PRIEST = "Priest"
    RANGER = "Ranger"
    ROGUE = "Rogue"
    WARLOCK = "Warlock"
    WARRIOR = "Warrior"

@unique
class Boss(Enum):
    FIRE = "fire"
    WATER = "water"
    BRUTE = "brute"
    THUNDER = "thunder"
    DRUID = "druid"
    SHADOW = "shadow"
    ICE = "ice"
    LIGHT = "light"
    ANCIENT = "ancient"
    DEMONIC = "demonic"

def max_bosses_in_difficulty(d: Difficulty) -> int:
    if d == Difficulty.VE:
        return 8
    if d == Difficulty.E:
        return 9
    if d == Difficulty.M:
        return 9
    if d == Difficulty.N:
        return 10
    if d == Difficulty.H:
        return 10

def difficulty_to_short_string(d: Difficulty) -> str:
    if d == Difficulty.VE:
        return "VE"
    if d == Difficulty.E:
        return "E"
    if d == Difficulty.M:
        return "M"
    if d == Difficulty.N:
        return "N"
    if d == Difficulty.H:
        return "H"

def replay_id_to_url(replay_id: int) -> str:
    return "https://impossible-bosses.github.io/ibstats/game/?id={}".format(replay_id)

class PlayerStats:
    def __init__(self, json: Any):
        self.deaths = json["deaths"]
        self.dmg = json["damage"]
        self.hl = json["healing"]
        self.hlr = json["healingReceived"]
        if "sWHealingReceived" not in json:
            # Data completeness issue
            self.hlrSw = None
        else:
            self.hlrSw = json["sWHealingReceived"]
        self.degen = json["degen"]

class PlayerData:
    name: str
    is_host: bool
    slot: int
    color: str
    class_: Class
    health: int
    mana: int
    ability: int
    ms: int
    coins: int
    stats_overall: PlayerStats
    boss_kills: int
    stats_boss: Any

    def __init__(self, json: Any) -> None:
        self.name = json["name"]
        self.is_host = json["isHost"]
        self.slot = json["slot"]
        self.color = json["colour"]
        mmd_vars = json["variables"]
        self.class_ = Class(mmd_vars["class"])
        self.health = mmd_vars["health"]
        self.mana = mmd_vars["mana"]
        self.ability = mmd_vars["ability"]
        self.ms = mmd_vars["movementSpeed"]
        self.coins = mmd_vars["coins"]
        self.stats_overall = PlayerStats(mmd_vars)
        self.boss_kills = 0
        self.stats_boss = {}
        for boss in Boss:
            mmd_vars_boss = {}
            for k, v in mmd_vars.items():
                if k[:len(boss.value)] == boss.value:
                    k_trim = k[len(boss.value)].lower() + k[len(boss.value)+1:]
                    mmd_vars_boss[k_trim] = v
            self.stats_boss[boss] = PlayerStats(mmd_vars_boss)
            if self.stats_boss[boss].deaths is not None:
                self.boss_kills += 1

class ReplayData:
    id: int
    game_name: str
    map: str
    host: str

    def __init__(self, json: Any) -> None:
        game = json["body"]["data"]["game"]
        self.id = json["body"]["id"]
        self.game_name = game["name"]
        self.map = game["map"][:-4]
        self.host = game["host"]

        flag = None
        difficulty = None
        continues = None
        for player in game["players"]:
            if len(player["flags"]) == 1:
                flag_player = player["flags"][0]
                if flag is None:
                    flag = flag_player
                elif flag_player is None:
                    continue
                elif flag != flag_player:
                    raise ValueError("Inconsistent flags: {} and {}".format(flag, flag_player))

            difficulty_player = player["variables"]["difficulty"]
            if difficulty is None:
                difficulty = difficulty_player
            elif difficulty_player is None:
                continue
            elif difficulty != difficulty_player:
                raise ValueError("Inconsistent difficulties: {} and {}".format(difficulty, difficulty_player))

            if "contines" in player["variables"]:
                # I had a typo in the IB map...
                continues_player = player["variables"]["contines"]
            else:
                continues_player = player["variables"]["continues"]
            if continues is None:
                continues = continues_player
            elif continues_player is None:
                continue
            elif continues != continues_player:
                raise ValueError("Inconsistent difficulties: {} and {}".format(continues, continues_player))

        if flag == "winner":
            self.win = True
        elif flag == "loser" or flag is None:
            self.win = False
        elif flag is None:
            raise ValueError("No flag values found")
        else:
            raise ValueError("Invalid flag: {}".format(flag))

        self.difficulty = Difficulty(difficulty)

        if continues == "yes":
            self.continues = True
        elif continues == "no":
            self.continues = False
        else:
            raise ValueError("Invalid continues: {}".format(continues))

        self.players = []
        for p in game["players"]:
            try:
                self.players.append(PlayerData(p))
            except ValueError:
                continue
        self.boss_kills = None
        if not self.win:
            self.boss_kills = max([p.boss_kills for p in self.players])

    def to_discord_embed(self) -> discord.Embed | None:
        if _class_emoji is None:
            logging.error("replays module used before loading emojis")
            return None

        title = "{} - {}".format(
            difficulty_to_short_string(self.difficulty),
            "Victory!" if self.win else "Defeat"
        )
        if not self.win:
            title += " ({}/{})".format(self.boss_kills, max_bosses_in_difficulty(self.difficulty))
        players_str = ""
        for player in self.players:
            players_str += "{} {}\n".format(_class_emoji[player.class_], player.name)

        embed = discord.Embed(title=title, description=players_str, url=replay_id_to_url(self.id))
        embed.set_footer(text=self.map)
        return embed

def replays_load_emojis(guild_emojis: list[discord.Emoji]) -> None:
    global _class_emoji
    _class_emoji = {}

    for emoji in guild_emojis:
        if emoji.name == "dk":
            _class_emoji[Class.DK] = emoji
        if emoji.name == "druid":
            _class_emoji[Class.DRUID] = emoji
        if emoji.name == "fm":
            _class_emoji[Class.FM] = emoji
        if emoji.name == "im":
            _class_emoji[Class.IM] = emoji
        if emoji.name == "pala":
            _class_emoji[Class.PALADIN] = emoji
        if emoji.name == "priest":
            _class_emoji[Class.PRIEST] = emoji
        if emoji.name == "ranger":
            _class_emoji[Class.RANGER] = emoji
        if emoji.name == "rog":
            _class_emoji[Class.ROGUE] = emoji
        if emoji.name == "wl":
            _class_emoji[Class.WARLOCK] = emoji
        if emoji.name == "demonwar":
            _class_emoji[Class.WARRIOR] = emoji

    if len(_class_emoji) != 10:
        raise Exception(f"Missing class emoji, {len(_class_emoji)}/10: ")
    logging.info("Loaded all class emoji for replays module")
