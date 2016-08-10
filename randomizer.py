from randomtools.tablereader import TableObject
from randomtools.utils import (
    classproperty, mutate_normal, shuffle_bits,
    utilrandom as random)
from randomtools.interface import (
    get_outfile, get_seed, get_flags, run_interface, rewrite_snes_meta,
    clean_and_write, finish_interface)
from os import path


VERSION = 1
ALL_OBJECTS = None


class StatObject:
    @property
    def character_id(self):
        return self.index % 5


class MonsterObject(TableObject):
    flag = "m"
    flag_description = "enemies"
    mutate_attributes = {
        "hp": (1, 32000),
        "speed": None,
        "attack": None,
        "defense": None,
        "magic_attack": None,
        "magic_defense": None,
        "fp": None,
        "evade": None,
        "magic_evade": None
        }
    intershuffle_attributes = [
            "hp", "speed", "attack", "defense", "magic_attack",
            "magic_defense", "fp", "evade", "magic_evade", "resistances",
            "immunities", "weaknesses_approach", "coin_anim_entrance",
        ]

    @property
    def rank(self):
        hp = self.hp if self.hp >= 10 else 100
        return hp * max(self.attack, self.magic_attack, 1)

    @property
    def intershuffle_valid(self):
        return not self.is_boss and self.rank >= 550

    @property
    def is_boss(self):
        return self.hit_special_defense & 0x02

    @classmethod
    def intershuffle(cls):
        super(MonsterObject, cls).intershuffle()
        valid = [m for m in cls.every if m.intershuffle_valid]
        hitspecs = [m.hit_special_defense & 0xFC for m in valid]
        random.shuffle(hitspecs)
        for hs, m in zip(hitspecs, valid):
            m.hit_special_defense = (m.hit_special_defense & 0x03) | hs

    def mutate(self):
        oldstats = {}
        for key in self.mutate_attributes:
            oldstats[key] = getattr(self, key)
        super(MonsterObject, self).mutate()
        if self.is_boss:
            for (attr, oldval) in oldstats.items():
                if getattr(self, attr) < oldval:
                    setattr(self, attr, oldval)


class MonsterAttackObject(TableObject): pass
class MonsterRewardObject(TableObject): pass
class PackObject(TableObject): pass
class FormationObject(TableObject): pass
class CharacterObject(TableObject): pass
class ItemObject(TableObject): pass
class LevelUpXPObject(TableObject): pass
class StatGrowthObject(StatObject, TableObject): pass
class StatBonusObject(StatObject, TableObject): pass
class SpellObject(TableObject): pass
class LearnObject(TableObject): pass
class WeaponTimingObject(TableObject): pass
class ShopObject(TableObject): pass
class FlowerBonusObject(TableObject): pass


if __name__ == "__main__":
    try:
        print ('You are using the Super Mario RPG '
               'randomizer version %s.' % VERSION)
        ALL_OBJECTS = [g for g in globals().values()
                       if isinstance(g, type) and issubclass(g, TableObject)
                       and g not in [TableObject]]
        run_interface(ALL_OBJECTS, snes=True)
        hexify = lambda x: "{0:0>2}".format("%x" % x)
        numify = lambda x: "{0: >3}".format(x)
        minmax = lambda x: (min(x), max(x))
        clean_and_write(ALL_OBJECTS)
        rewrite_snes_meta("SMRPG-R", VERSION, megabits=32, lorom=True)
        finish_interface()
        import pdb; pdb.set_trace()
    except Exception, e:
        print "ERROR: %s" % e
        raw_input("Press Enter to close this program.")
