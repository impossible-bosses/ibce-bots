import discord
import logging

BELL_EMOJI = "\U0001F514"
NOBELL_EMOJI = "\U0001F515"

class MapVersion:
    def __init__(self, file_name, ent_only=False, deprecated=True, counterfeit=False, slots=[8,11]):
        self.file_name = file_name
        self.ent_only = ent_only
        self.deprecated = deprecated
        self.counterfeit = counterfeit
        self.slots = slots

KNOWN_VERSIONS = [
    MapVersion("Impossible.Bosses.v1.12.3", deprecated=False),
    MapVersion("Impossible.Bosses.v1.12.3-no-bnet", ent_only=True, deprecated=False),
    MapVersion("Impossible.Bosses.v1.12.2"),
    MapVersion("Impossible.Bosses.v1.12.2-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.12.1"),
    MapVersion("Impossible.Bosses.v1.12.1-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.12.0"),
    MapVersion("Impossible.Bosses.v1.12.0-no-bnet", ent_only=True),

    MapVersion("Impossible.Bosses.v1.11.22"),
    MapVersion("Impossible.Bosses.v1.11.22-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.21"),
    MapVersion("Impossible.Bosses.v1.11.21-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.20"),
    MapVersion("Impossible.Bosses.v1.11.20-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.9"),
    MapVersion("Impossible.Bosses.v1.11.9-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.8"),
    MapVersion("Impossible.Bosses.v1.11.8-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.7"),
    MapVersion("Impossible.Bosses.v1.11.7-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.6"),
    MapVersion("Impossible.Bosses.v1.11.6-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.5-no-bnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.4-nobnet", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.3-ent", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.2-ent", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.1-ent", ent_only=True),
    MapVersion("Impossible.Bosses.v1.11.0-ent", ent_only=True),

    MapVersion("Impossible.Bosses.v1.10.5"),
    MapVersion("Impossible.Bosses.v1.10.5-ent", ent_only=True),
    MapVersion("Impossible.Bosses.v1.10.4-ent", ent_only=True),
    MapVersion("Impossible.Bosses.v1.10.3-ent", ent_only=True),
    MapVersion("Impossible.Bosses.v1.10.2-ent", ent_only=True),
    MapVersion("Impossible.Bosses.v1.10.1-ent", ent_only=True),

    MapVersion("Impossible_BossesReforgedV1.09Test"),
    MapVersion("ImpossibleBossesEnt1.09", ent_only=True),
    MapVersion("Impossible_BossesReforgedV1.09_UFWContinues", counterfeit=True),
    MapVersion("Impossible_BossesReforgedV1.09UFW30", counterfeit=True),
    MapVersion("Impossible_BossesReforgedV1.08Test"),
    MapVersion("Impossible_BossesReforgedV1.07Test"),
    MapVersion("Impossible_BossesTestversion1.06"),
    MapVersion("Impossible_BossesReforgedV1.05"),
    MapVersion("Impossible_BossesReforgedV1.02"),

    MapVersion("Impossible Bosses BetaV3V"),
    MapVersion("Impossible Bosses BetaV3R"),
    MapVersion("Impossible Bosses BetaV3P"),
    MapVersion("Impossible Bosses BetaV3E"),
    MapVersion("Impossible Bosses BetaV3C"),
    MapVersion("Impossible Bosses BetaV3A"),
    MapVersion("Impossible Bosses BetaV2X"),
    MapVersion("Impossible Bosses BetaV2W"),
    MapVersion("Impossible Bosses BetaV2S"),
    MapVersion("Impossible Bosses BetaV2J"),
    MapVersion("Impossible Bosses BetaV2F"),
    MapVersion("Impossible Bosses BetaV2E"),
    MapVersion("Impossible Bosses BetaV2D"),
    MapVersion("Impossible Bosses BetaV2C"),
    MapVersion("Impossible Bosses BetaV2A"),
    MapVersion("Impossible Bosses BetaV1Y"),
    MapVersion("Impossible Bosses BetaV1X"),
    MapVersion("Impossible Bosses BetaV1W"),
    MapVersion("Impossible Bosses BetaV1V"),
    MapVersion("Impossible Bosses BetaV1R"),
    MapVersion("Impossible Bosses BetaV1P"),
    MapVersion("Impossible Bosses BetaV1C"),
]

def get_map_version(map_file):
    for version in KNOWN_VERSIONS:
        if map_file == version.file_name:
            return version
    return None

def get_map_server_nice(server):
    if server == "usw":
        return ":flag_us: US"
    elif server == "eu":
        return ":flag_eu: EU"
    elif server == "kr":
        return ":flag_kr: KR"
    elif server == "Montreal":
        return ":flag_ca: Montreal (ENT)"
    elif server == "New York":
        return ":flag_us: New York (ENT)"
    elif server == "France":
        return ":flag_fr: France (ENT)"
    elif server == "Amsterdam":
        return ":flag_nl: Amsterdam (ENT)"
    return server

class Lobby:
    def __init__(self, lobby_dict, is_ent):
        self.is_ent = is_ent
        self.id = lobby_dict["id"]
        self.name = lobby_dict["name"]
        self.map = lobby_dict["map"]
        self.host = lobby_dict["host"]
        self.subscribers = []

        if is_ent:
            self.server = lobby_dict["location"]
            self.slots_taken = lobby_dict["slots_taken"]
            self.slots_total = lobby_dict["slots_total"]
        else:
            if self.map[-4:] == ".w3x":
                self.map = self.map[:-4]
            self.server = lobby_dict["server"]
            self.slots_taken = lobby_dict["slotsTaken"]
            self.slots_total = lobby_dict["slotsTotal"]

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return self.id

    def __str__(self):
        return "[id={} ent={} name=\"{}\" server={} map=\"{}\" host={} slots={}/{}]".format(
            self.id, self.is_ent, self.name, self.server, self.map, self.host, self.slots_taken, self.slots_total
        )

    def get_message_id_key(self):
        return "lobbymsg{}".format(self.id)

    def is_ib(self):
        # return self.map.find("Legion") != -1 and self.map.find("TD") != -1 # test
        #return self.map.find("Uther Party") != -1 # test
        return self.map.find("Impossible") != -1 and self.map.find("Bosses") != -1

    def is_updated(self, new):
        return self.name != new.name or self.server != new.server or self.map != new.map or self.host != new.host or self.slots_taken != new.slots_taken or self.slots_total != new.slots_total

    def to_discord_message_info(self, bnet_lobby_role, is_open):
        COLOR_CLOSED = discord.Colour(0x8a0808)

        version = get_map_version(self.map)
        mark = ""
        message = ""
        if version is None:
            mark = ":question:"
            message = ":warning: *Unknown map version* :warning:"
        elif version.counterfeit:
            mark = ":x:"
            message = ":warning: *Counterfeit version* :warning:"
        elif not self.is_ent and version.ent_only:
            mark = ":x:"
            message = ":warning: *Incompatible version* :warning:"
        elif version.deprecated:
            mark = ":x:"
            message = ":warning: *Old map version* :warning:"
        if not self.is_ent:
            if len(message) > 0:
                message += "\n"
            message += f"{bnet_lobby_role.mention}"

        slots_taken = self.slots_taken
        slots_total = self.slots_total

        if version is not None:
            if not self.is_ent:
                # Not sure why, but IB bnet lobbies have 1 extra slot
                slots_total -= 1

            if slots_total not in version.slots:
                logging.error("Invalid total slots {}, expected {}, for map file {}".format(self.slots_total, version.slots, self.map))
                return None

        title_format = "{} ({}/{})"
        description_format = "{} {}"
        if not is_open:
            title_format = "~~{}~~ ({}/{})"
            description_format = "~~{}~~ {}"

        title = title_format.format(self.name, slots_taken, slots_total)
        description = description_format.format(self.map, mark)
        host = self.host if len(self.host) > 0 else "---"
        server = get_map_server_nice(self.server)

        embed = discord.Embed(title=title, description=description)
        embed.add_field(name="Host", value=host, inline=True)
        embed.add_field(name="Server", value=server, inline=True)
        if len(self.subscribers) > 0:
            subscribers_string = BELL_EMOJI + " "
            for i in range(0, len(self.subscribers), 4):
                if i != 0:
                    subscribers_string += "\n"
                subscribers_string += ", ".join([
                    sub.display_name for sub in self.subscribers[i:i+4]
                ])

            embed.set_footer(text=subscribers_string)

        if not is_open:
            embed.color = COLOR_CLOSED

        return {
            "message": message,
            "embed": embed,
        }
