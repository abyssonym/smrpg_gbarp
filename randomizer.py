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


class MonsterObject(TableObject): pass
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
        rewrite_snes_meta("SMRPG-R", VERSION, megabits=24, lorom=True)
        finish_interface()
        for w in WeaponTimingObject.every:
            print "%x" % w.index, " ".join(map(hexify, w.timings))
        import pdb; pdb.set_trace()
    except Exception, e:
        print "ERROR: %s" % e
        raw_input("Press Enter to close this program.")
